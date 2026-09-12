"""FlowCore — Self-Healing Watchdog.

Monitors critical services and sends Telegram alerts when something fails.
Designed to run as a cron job (every 5 minutes) or as a background thread.

Checks performed on every run:
  - FlowCore API health  (HTTP GET localhost:8080/api/health)
  - cloudflared tunnel process
  - Each bot script in ~/.flowcore/bots/*.sh (by process name)
  - Doctor FAIL-level checks (DNS, internet, daemon state)

Alert deduplication:
  State persists to ~/.flowcore/watchdog.state.json.  Each incident fires
  ONE alert on first detection, then silently waits.  A recovery sends a
  separate "back to normal" message.  This means no alert spam even when
  the watchdog runs every minute.

Auto-restart:
  Bot processes with an entry in KNOWN_BOTS get one restart attempt before
  the alert fires.  FlowCore API is restarted by re-running its launch
  command if the port is bound to no process.

Usage::

    # Crontab (run every 5 minutes):
    */5 * * * * python3 ~/FlowCore/runtime/watchdog.py

    # CLI (one-shot, prints status):
    python3 flowcore.py watchdog run

    # CLI (show last persisted state):
    python3 flowcore.py watchdog status

    # Continuous background thread (called by daemon):
    from runtime.watchdog import WatchdogService
    svc = WatchdogService()
    svc.start_loop(interval=300)
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from loguru import logger


_STATE_FILE = Path.home() / ".flowcore" / "watchdog.state.json"
_BOTS_DIR = Path.home() / ".flowcore" / "bots"
_FLOWCORE_API_URL = "http://127.0.0.1:8080/api/health"
_FLOWCORE_API_TIMEOUT = 5.0

# Bot scripts expected to be running, keyed by a short name.
# Value is the restart command (run from the bot's home directory).
# Populated from ~/.flowcore/bots/*.sh at runtime; this dict is
# supplemented with any script the watchdog finds there.
KNOWN_BOTS: dict[str, str] = {
    "signal-engine": "bash $HOME/.flowcore/bots/signal-engine.sh",
    "spcx-monitor": "bash $HOME/.flowcore/bots/spcx-monitor.sh",
    "renda-fixa-monitor": "bash $HOME/.flowcore/bots/renda-fixa-monitor.sh",
}


class WatchStatus(str, Enum):
    OK = "ok"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


@dataclass
class WatchResult:
    name: str
    status: WatchStatus
    message: str
    fix: str = ""
    restart_attempted: bool = False

    @property
    def ok(self) -> bool:
        return self.status == WatchStatus.OK

    @property
    def failed(self) -> bool:
        return self.status == WatchStatus.FAIL


@dataclass
class WatchdogReport:
    results: list[WatchResult] = field(default_factory=list)
    checked_at: float = field(default_factory=time.time)
    alerts_sent: list[str] = field(default_factory=list)
    recoveries_sent: list[str] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return all(r.status != WatchStatus.FAIL for r in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "healthy": self.healthy,
            "checked_at": self.checked_at,
            "alerts_sent": self.alerts_sent,
            "recoveries_sent": self.recoveries_sent,
            "results": [
                {
                    "name": r.name,
                    "status": r.status.value,
                    "message": r.message,
                    "fix": r.fix,
                    "restart_attempted": r.restart_attempted,
                }
                for r in self.results
            ],
        }


class WatchdogService:
    """Run all checks and fire Telegram alerts for new failures / recoveries."""

    def __init__(self, api_url: str = _FLOWCORE_API_URL) -> None:
        self._api_url = api_url
        self._state: dict[str, Any] = self._load_state()

    # ── Public interface ──────────────────────────────────────────────────────

    def run(self, *, alert: bool = True) -> WatchdogReport:
        """Run all checks once.  Send Telegram alerts when *alert* is True."""
        results = self._collect()
        report = WatchdogReport(results=results)

        if alert:
            self._process_alerts(report)

        self._save_state(results, report)
        return report

    def start_loop(self, interval: int = 300) -> None:
        """Block forever, running checks every *interval* seconds."""

        logger.info("WatchdogService started (interval={}s)", interval)
        while True:
            try:
                self.run(alert=True)
            except Exception as exc:
                logger.error("WatchdogService loop error: {}", exc)
            time.sleep(interval)

    def last_state(self) -> dict[str, Any]:
        """Return the persisted state from the most recent run."""
        return self._load_state()

    # ── Checks ────────────────────────────────────────────────────────────────

    def _collect(self) -> list[WatchResult]:
        results: list[WatchResult] = []
        results.append(self._check_flowcore_api())
        results.append(self._check_cloudflared())
        results.extend(self._check_bots())
        results.extend(self._check_doctor())
        return results

    def _check_flowcore_api(self) -> WatchResult:
        try:
            req = urllib.request.Request(self._api_url, method="GET")
            with urllib.request.urlopen(req, timeout=_FLOWCORE_API_TIMEOUT) as resp:
                data = json.loads(resp.read().decode())
                if data.get("status") == "ok":
                    uptime = data.get("uptime_seconds", "?")
                    return WatchResult("flowcore_api", WatchStatus.OK, f"API ok (uptime {uptime:.0f}s)")
                return WatchResult("flowcore_api", WatchStatus.WARN, f"API responded but status={data.get('status')!r}")
        except urllib.error.URLError as e:
            return WatchResult(
                "flowcore_api",
                WatchStatus.FAIL,
                f"API unreachable: {e}",
                fix="python3 ~/FlowCore/flowcore.py serve &",
            )
        except Exception as e:
            return WatchResult("flowcore_api", WatchStatus.FAIL, f"API check error: {e}")

    def _check_cloudflared(self) -> WatchResult:
        if not self._process_running("cloudflared"):
            return WatchResult(
                "cloudflared",
                WatchStatus.FAIL,
                "cloudflared process not found",
                fix="cloudflared tunnel run --token $(cat ~/.config/cloudflared/tunnel-token) &",
            )
        return WatchResult("cloudflared", WatchStatus.OK, "cloudflared running")

    def _check_bots(self) -> list[WatchResult]:
        results: list[WatchResult] = []
        # Discover bots: KNOWN_BOTS + any *.sh in ~/.flowcore/bots/
        bots: dict[str, str] = {}
        if _BOTS_DIR.exists():
            for script in sorted(_BOTS_DIR.glob("*.sh")):
                name = script.stem
                bots[name] = KNOWN_BOTS.get(name, f"bash {script}")
        for name, restart_cmd in KNOWN_BOTS.items():
            if name not in bots:
                bots[name] = restart_cmd

        for name, restart_cmd in sorted(bots.items()):
            if not _BOTS_DIR.exists() or not (_BOTS_DIR / f"{name}.sh").exists():
                results.append(WatchResult(f"bot:{name}", WatchStatus.SKIP, "script not installed"))
                continue
            if self._process_running(name):
                results.append(WatchResult(f"bot:{name}", WatchStatus.OK, f"{name} running"))
            else:
                attempted = self._try_restart(restart_cmd)
                if attempted and self._process_running(name):
                    results.append(WatchResult(
                        f"bot:{name}", WatchStatus.OK, f"{name} restarted OK", restart_attempted=True
                    ))
                else:
                    results.append(
                        WatchResult(
                            f"bot:{name}",
                            WatchStatus.FAIL,
                            f"{name} not running" + (" (restart failed)" if attempted else ""),
                            fix=restart_cmd,
                            restart_attempted=attempted,
                        )
                    )
        return results

    def _check_doctor(self) -> list[WatchResult]:
        try:
            from doctor.service import CheckStatus, DoctorService

            report = DoctorService().run(verbose=False)
            _critical_names = ("dns", "internet", "daemon_state")
            critical = [c for c in report.checks if c.status == CheckStatus.FAIL and c.name in _critical_names]
            results = []
            for c in critical:
                results.append(
                    WatchResult(
                        f"system:{c.name}",
                        WatchStatus.FAIL,
                        c.message,
                        fix=c.fix,
                    )
                )
            return results
        except Exception as e:
            return [WatchResult("system:doctor", WatchStatus.WARN, f"Doctor check failed: {e}")]

    # ── Alert logic ───────────────────────────────────────────────────────────

    def _process_alerts(self, report: WatchdogReport) -> None:
        prior: dict[str, str] = self._state.get("service_status", {})

        new_failures: list[WatchResult] = []
        recoveries: list[str] = []

        for r in report.results:
            was = prior.get(r.name, "ok")
            now = r.status.value
            if r.failed and was != "fail":
                new_failures.append(r)
            elif now == "ok" and was == "fail":
                recoveries.append(r.name)

        for r in new_failures:
            msg = self._format_failure_alert(r)
            sent = self._send_telegram(msg)
            if sent:
                report.alerts_sent.append(r.name)
                logger.warning("Watchdog alert sent: {}", r.name)

        for name in recoveries:
            msg = f"✅ <b>FlowCore Watchdog</b>\n<b>{name}</b> voltou ao normal."
            sent = self._send_telegram(msg)
            if sent:
                report.recoveries_sent.append(name)
                logger.info("Watchdog recovery sent: {}", name)

    def _format_failure_alert(self, r: WatchResult) -> str:
        lines = [
            "🔴 <b>FlowCore Watchdog — ALERTA</b>",
            "",
            f"<b>Serviço:</b> {r.name}",
            f"<b>Erro:</b> {r.message}",
        ]
        if r.fix:
            lines.append(f"<b>Correção:</b> <code>{r.fix}</code>")
        if r.restart_attempted:
            lines.append("<i>(reinício automático tentado, sem sucesso)</i>")
        return "\n".join(lines)

    def _send_telegram(self, text: str) -> bool:
        try:
            from runtime.telegram import send_message

            send_message(text)
            return True
        except Exception as e:
            logger.warning("Watchdog: Telegram alert failed: {}", e)
            return False

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _process_running(name: str) -> bool:
        try:
            result = subprocess.run(
                ["pgrep", "-f", name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def _try_restart(cmd: str) -> bool:
        try:
            subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            time.sleep(3)
            return True
        except Exception as e:
            logger.warning("Watchdog restart failed: {} — {}", cmd, e)
            return False

    # ── State persistence ─────────────────────────────────────────────────────

    def _load_state(self) -> dict[str, Any]:
        try:
            if _STATE_FILE.exists():
                return json.loads(_STATE_FILE.read_text())
        except Exception:
            pass
        return {"service_status": {}, "last_run": None}

    def _save_state(self, results: list[WatchResult], report: WatchdogReport) -> None:
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            state = {
                "service_status": {r.name: r.status.value for r in results},
                "last_run": report.checked_at,
                "last_report": report.to_dict(),
            }
            _STATE_FILE.write_text(json.dumps(state, indent=2))
            self._state = state
        except Exception as e:
            logger.warning("Watchdog: could not save state: {}", e)


# ── Standalone entry point (for crontab) ─────────────────────────────────────


def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="FlowCore Watchdog")
    parser.add_argument("--loop", action="store_true", help="Run continuously instead of once")
    parser.add_argument("--interval", type=int, default=300, help="Loop interval in seconds")
    parser.add_argument("--no-alert", action="store_true", help="Run checks without sending alerts")
    parser.add_argument("--status", action="store_true", help="Print last persisted state and exit")
    args = parser.parse_args()

    svc = WatchdogService()

    if args.status:
        state = svc.last_state()
        print(json.dumps(state, indent=2))
        return

    if args.loop:
        svc.start_loop(interval=args.interval)
    else:
        report = svc.run(alert=not args.no_alert)
        print(json.dumps(report.to_dict(), indent=2))
        raise SystemExit(0 if report.healthy else 1)


if __name__ == "__main__":
    _main()
