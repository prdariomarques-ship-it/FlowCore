"""FlowCore Doctor Service — comprehensive runtime health validation.

Runs 25+ checks across Android, Termux, system tools, permissions,
network connectivity, and AI bridges.  Every check returns a CheckResult
with a status, human-readable message, and optional fix suggestion.

DoctorService is a service, not a one-shot script.  It can be run at boot
(called by RuntimeKernel), on demand via CLI, or periodically in the
background.

Usage::

    doctor = DoctorService()
    report = doctor.run()
    for check in report.checks:
        print(check.name, check.status, check.message)
"""

from __future__ import annotations

import os
import socket
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

from loguru import logger
from runtime.ollama import OllamaDiscoveryError, discover_ollama_endpoint
from runtime.shell import is_available, run, which


# ── Result types ──────────────────────────────────────────────────────────────


class CheckStatus(str, Enum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    message: str
    fix: str = ""  # suggested remediation command or instruction

    @property
    def ok(self) -> bool:
        return self.status == CheckStatus.OK

    @property
    def failed(self) -> bool:
        return self.status == CheckStatus.FAIL


@dataclass
class DoctorReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.OK)

    @property
    def warned(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.WARN)

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.FAIL)

    @property
    def healthy(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "warned": self.warned,
            "failed": self.failed,
            "healthy": self.healthy,
            "checks": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    "fix": c.fix,
                }
                for c in self.checks
            ],
        }


# ── Doctor Service ────────────────────────────────────────────────────────────


class DoctorService:
    """Runs all health checks and returns a DoctorReport."""

    def __init__(self) -> None:
        self._checks: list[Callable[[], CheckResult]] = [
            # ── Android / Termux ─────────────────────────────────────────────
            self._check_android_detected,
            self._check_android_version,
            self._check_termux_detected,
            self._check_termux_api,
            self._check_termux_storage,
            self._check_termux_pkg,
            # ── Android capability probes ─────────────────────────────────────
            self._check_wakelock,
            self._check_camera,
            self._check_microphone,
            self._check_location,
            self._check_bluetooth,
            self._check_vibrate,
            self._check_torch,
            self._check_share,
            # ── Core tools ───────────────────────────────────────────────────
            self._check_python3,
            self._check_pip,
            self._check_git,
            self._check_ssh,
            self._check_sqlite3,
            self._check_curl,
            self._check_jq,
            # ── Android permissions (heuristic) ──────────────────────────────
            self._check_notification_permission,
            self._check_battery_optimization,
            # ── Network ──────────────────────────────────────────────────────
            self._check_dns,
            self._check_internet,
            self._check_oracle_reachable,
            self._check_docker_reachable,
            self._check_mcp_reachable,
            # ── AI Bridges ───────────────────────────────────────────────────
            self._check_ollama,
            # ── Telegram Bots ────────────────────────────────────────────────
            self._check_telegram_dario_os,
            self._check_telegram_b3,
            # ── Termux Runtime (Sprint 10) ───────────────────────────────────
            self._check_rsync,
            self._check_cron,
            self._check_termux_boot,
            self._check_daemon_state,
            # ── Runtime state ────────────────────────────────────────────────
            self._check_runtime_json,
            self._check_flowcore_config,
        ]
        self._running = False
        self._thread: threading.Thread | None = None

    def start_service(self, interval: int = 300) -> None:
        """Run Doctor continuously in a background thread.

        Checks are repeated every *interval* seconds (default: 5 minutes).
        Call stop_service() to terminate the loop.
        """
        if self._running:
            logger.warning("DoctorService already running")
            return
        self._running = True

        def _loop() -> None:
            logger.info("DoctorService started (interval={}s)", interval)
            while self._running:
                try:
                    report = self.run(verbose=False)
                    if not report.healthy:
                        failures = [c.name for c in report.checks if c.failed]
                        logger.warning("DoctorService: unhealthy — failed checks: {}", failures)
                except Exception as exc:
                    logger.error("DoctorService loop error: {}", exc)
                for _ in range(interval * 10):
                    if not self._running:
                        break
                    time.sleep(0.1)
            logger.info("DoctorService stopped")

        self._thread = threading.Thread(target=_loop, daemon=True, name="flowcore-doctor")
        self._thread.start()

    def stop_service(self) -> None:
        """Stop the background Doctor loop."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    @property
    def is_running(self) -> bool:
        return self._running and (self._thread is not None) and self._thread.is_alive()

    def run(self, *, verbose: bool = False) -> DoctorReport:
        """Execute all checks and return the consolidated report."""
        report = DoctorReport()
        for check_fn in self._checks:
            try:
                result = check_fn()
            except Exception as exc:
                result = CheckResult(
                    name=check_fn.__name__.replace("_check_", ""),
                    status=CheckStatus.FAIL,
                    message=f"Check raised exception: {exc}",
                )
            report.checks.append(result)
            if verbose:
                icon = {"ok": "✓", "warn": "⚠", "fail": "✗", "skip": "─"}[result.status.value]
                logger.info("  {} {} — {}", icon, result.name, result.message)

        logger.info(
            "Doctor: {}/{} checks passed ({} warnings, {} failures)",
            report.passed,
            len(report.checks),
            report.warned,
            report.failed,
        )
        return report

    # ── Android / Termux checks ───────────────────────────────────────────────

    def _check_android_detected(self) -> CheckResult:
        detected = bool(os.environ.get("PREFIX")) or os.path.exists("/system/bin/app_process")
        if detected:
            return CheckResult("android_detected", CheckStatus.OK, "Android environment detected")
        return CheckResult("android_detected", CheckStatus.SKIP, "Not running on Android")

    def _check_android_version(self) -> CheckResult:
        if not is_available("getprop"):
            return CheckResult("android_version", CheckStatus.SKIP, "getprop not available")
        result = run(["getprop", "ro.build.version.release"], timeout=3)
        if result.success and result.stdout.strip():
            ver = result.stdout.strip()
            sdk_result = run(["getprop", "ro.build.version.sdk"], timeout=3)
            sdk = sdk_result.stdout.strip() if sdk_result.success else "?"
            return CheckResult("android_version", CheckStatus.OK, f"Android {ver} (SDK {sdk})")
        return CheckResult("android_version", CheckStatus.WARN, "Could not read Android version")

    def _check_termux_detected(self) -> CheckResult:
        prefix = os.environ.get("PREFIX", "")
        if prefix and os.path.exists(prefix + "/bin/bash"):
            return CheckResult("termux_detected", CheckStatus.OK, f"Termux prefix: {prefix}")
        return CheckResult("termux_detected", CheckStatus.SKIP, "Not running in Termux")

    def _check_termux_api(self) -> CheckResult:
        if not os.environ.get("PREFIX"):
            return CheckResult("termux_api", CheckStatus.SKIP, "Not in Termux")
        if is_available("termux-battery-status"):
            return CheckResult("termux_api", CheckStatus.OK, "Termux:API installed")
        return CheckResult(
            "termux_api",
            CheckStatus.WARN,
            "Termux:API not installed — Android capabilities unavailable",
            fix="pkg install termux-api",
        )

    def _check_termux_storage(self) -> CheckResult:
        if not os.environ.get("PREFIX"):
            return CheckResult("termux_storage", CheckStatus.SKIP, "Not in Termux")
        storage = Path.home() / "storage"
        if storage.exists():
            return CheckResult("termux_storage", CheckStatus.OK, "Termux storage set up")
        return CheckResult(
            "termux_storage",
            CheckStatus.WARN,
            "Termux storage not configured",
            fix="termux-setup-storage",
        )

    def _check_termux_pkg(self) -> CheckResult:
        if not os.environ.get("PREFIX"):
            return CheckResult("termux_pkg", CheckStatus.SKIP, "Not in Termux")
        if is_available("pkg"):
            return CheckResult("termux_pkg", CheckStatus.OK, "pkg package manager available")
        return CheckResult("termux_pkg", CheckStatus.FAIL, "pkg not found in Termux")

    # ── Android capability probes ─────────────────────────────────────────────

    def _check_wakelock(self) -> CheckResult:
        if not os.environ.get("PREFIX"):
            return CheckResult("wakelock", CheckStatus.SKIP, "Not in Termux")
        if is_available("termux-wake-lock"):
            return CheckResult("wakelock", CheckStatus.OK, "termux-wake-lock available")
        return CheckResult(
            "wakelock",
            CheckStatus.WARN,
            "termux-wake-lock not found — background tasks may be killed",
            fix="pkg install termux-api",
        )

    def _check_camera(self) -> CheckResult:
        if not os.environ.get("PREFIX"):
            return CheckResult("camera", CheckStatus.SKIP, "Not in Termux")
        if is_available("termux-camera-photo"):
            return CheckResult("camera", CheckStatus.OK, "termux-camera-photo available")
        return CheckResult(
            "camera",
            CheckStatus.WARN,
            "termux-camera-photo not found",
            fix="pkg install termux-api",
        )

    def _check_microphone(self) -> CheckResult:
        if not os.environ.get("PREFIX"):
            return CheckResult("microphone", CheckStatus.SKIP, "Not in Termux")
        if is_available("termux-microphone-record"):
            return CheckResult("microphone", CheckStatus.OK, "termux-microphone-record available")
        return CheckResult(
            "microphone",
            CheckStatus.WARN,
            "termux-microphone-record not found",
            fix="pkg install termux-api",
        )

    def _check_location(self) -> CheckResult:
        if not os.environ.get("PREFIX"):
            return CheckResult("location", CheckStatus.SKIP, "Not in Termux")
        if is_available("termux-location"):
            return CheckResult("location", CheckStatus.OK, "termux-location available")
        return CheckResult(
            "location",
            CheckStatus.WARN,
            "termux-location not found",
            fix="pkg install termux-api",
        )

    def _check_bluetooth(self) -> CheckResult:
        if not os.environ.get("PREFIX"):
            return CheckResult("bluetooth", CheckStatus.SKIP, "Not in Termux")
        if is_available("termux-bluetooth-get-adapters"):
            return CheckResult("bluetooth", CheckStatus.OK, "termux-bluetooth-get-adapters available")
        # Distinguish: termux-api not installed vs. tool absent on this Android version
        if not is_available("termux-battery-status"):
            return CheckResult(
                "bluetooth",
                CheckStatus.WARN,
                "Termux:API not installed — Bluetooth unavailable",
                fix="pkg install termux-api",
            )
        return CheckResult(
            "bluetooth",
            CheckStatus.SKIP,
            "Bluetooth API not available on this Android version (termux-bluetooth-get-adapters absent)",
        )

    def _check_vibrate(self) -> CheckResult:
        if not os.environ.get("PREFIX"):
            return CheckResult("vibrate", CheckStatus.SKIP, "Not in Termux")
        if is_available("termux-vibrate"):
            return CheckResult("vibrate", CheckStatus.OK, "termux-vibrate available")
        return CheckResult(
            "vibrate",
            CheckStatus.WARN,
            "termux-vibrate not found",
            fix="pkg install termux-api",
        )

    def _check_torch(self) -> CheckResult:
        if not os.environ.get("PREFIX"):
            return CheckResult("torch", CheckStatus.SKIP, "Not in Termux")
        if is_available("termux-torch"):
            return CheckResult("torch", CheckStatus.OK, "termux-torch available")
        return CheckResult(
            "torch",
            CheckStatus.WARN,
            "termux-torch not found",
            fix="pkg install termux-api",
        )

    def _check_share(self) -> CheckResult:
        if not os.environ.get("PREFIX"):
            return CheckResult("share", CheckStatus.SKIP, "Not in Termux")
        if is_available("termux-share"):
            return CheckResult("share", CheckStatus.OK, "termux-share available")
        return CheckResult(
            "share",
            CheckStatus.WARN,
            "termux-share not found",
            fix="pkg install termux-api",
        )

    # ── Core tools ────────────────────────────────────────────────────────────

    def _check_python3(self) -> CheckResult:
        p = which("python3") or which("python")
        if not p:
            return CheckResult(
                "python3",
                CheckStatus.FAIL,
                "python3 not found",
                fix="pkg install python || apt-get install python3",
            )
        result = run([p, "--version"], timeout=5)
        ver = result.stdout.strip() or result.stderr.strip()
        return CheckResult("python3", CheckStatus.OK, f"{ver} at {p}")

    def _check_pip(self) -> CheckResult:
        python = which("python3") or which("python")
        if not python:
            return CheckResult("pip", CheckStatus.SKIP, "python3 not found")
        result = run([python, "-m", "pip", "--version"], timeout=5)
        if result.success:
            return CheckResult("pip", CheckStatus.OK, result.stdout.strip())
        return CheckResult(
            "pip",
            CheckStatus.WARN,
            "pip not available",
            fix="python3 -m ensurepip --upgrade",
        )

    def _check_git(self) -> CheckResult:
        if not is_available("git"):
            return CheckResult(
                "git",
                CheckStatus.WARN,
                "git not found",
                fix="pkg install git || apt-get install git",
            )
        result = run(["git", "--version"], timeout=5)
        return CheckResult("git", CheckStatus.OK, result.stdout.strip())

    def _check_ssh(self) -> CheckResult:
        if not is_available("ssh"):
            return CheckResult(
                "ssh",
                CheckStatus.WARN,
                "ssh not found",
                fix="pkg install openssh || apt-get install openssh-client",
            )
        return CheckResult("ssh", CheckStatus.OK, f"ssh at {which('ssh')}")

    def _check_sqlite3(self) -> CheckResult:
        if not is_available("sqlite3"):
            return CheckResult(
                "sqlite3",
                CheckStatus.WARN,
                "sqlite3 CLI not found",
                fix="pkg install sqlite || apt-get install sqlite3",
            )
        result = run(["sqlite3", "--version"], timeout=5)
        return CheckResult("sqlite3", CheckStatus.OK, result.stdout.strip())

    def _check_curl(self) -> CheckResult:
        if not is_available("curl"):
            return CheckResult(
                "curl",
                CheckStatus.WARN,
                "curl not found",
                fix="pkg install curl || apt-get install curl",
            )
        result = run(["curl", "--version"], timeout=5)
        first_line = result.stdout.strip().splitlines()[0] if result.stdout else "curl available"
        return CheckResult("curl", CheckStatus.OK, first_line)

    def _check_jq(self) -> CheckResult:
        if not is_available("jq"):
            return CheckResult(
                "jq",
                CheckStatus.WARN,
                "jq not found (optional)",
                fix="pkg install jq || apt-get install jq",
            )
        result = run(["jq", "--version"], timeout=5)
        return CheckResult("jq", CheckStatus.OK, result.stdout.strip())

    # ── Permission heuristics ─────────────────────────────────────────────────

    def _check_notification_permission(self) -> CheckResult:
        if not os.environ.get("PREFIX"):
            return CheckResult("notification_permission", CheckStatus.SKIP, "Not in Termux")
        if is_available("termux-notification"):
            return CheckResult("notification_permission", CheckStatus.OK, "termux-notification available")
        return CheckResult(
            "notification_permission",
            CheckStatus.WARN,
            "Cannot verify notification permission — termux-api not installed",
            fix="pkg install termux-api",
        )

    def _check_battery_optimization(self) -> CheckResult:
        if not os.environ.get("PREFIX"):
            return CheckResult("battery_optimization", CheckStatus.SKIP, "Not in Termux")
        # We can't query this from shell; inform the user to check manually
        return CheckResult(
            "battery_optimization",
            CheckStatus.WARN,
            "Cannot verify battery optimization from shell — check manually",
            fix="Settings → Battery → FlowCore/Termux → Unrestricted",
        )

    # ── Network ───────────────────────────────────────────────────────────────

    def _check_dns(self) -> CheckResult:
        try:
            socket.getaddrinfo("8.8.8.8", None, socket.AF_INET)
            return CheckResult("dns", CheckStatus.OK, "DNS resolution working")
        except Exception as e:
            return CheckResult("dns", CheckStatus.FAIL, f"DNS failed: {e}")

    def _check_internet(self) -> CheckResult:
        try:
            with socket.create_connection(("google.com", 443), timeout=5):
                return CheckResult("internet", CheckStatus.OK, "Internet reachable")
        except Exception as e:
            return CheckResult("internet", CheckStatus.WARN, f"Internet unreachable: {e}")

    def _check_oracle_reachable(self) -> CheckResult:
        host = os.environ.get("FLOWCORE_ORACLE_HOST", "")
        if not host:
            return CheckResult("oracle_reachable", CheckStatus.SKIP, "FLOWCORE_ORACLE_HOST not set")
        try:
            with socket.create_connection((host, 443), timeout=5):
                return CheckResult("oracle_reachable", CheckStatus.OK, f"Oracle reachable at {host}")
        except Exception as e:
            return CheckResult(
                "oracle_reachable",
                CheckStatus.WARN,
                f"Oracle unreachable at {host}: {e}",
                fix=f"Check FLOWCORE_ORACLE_HOST and network connectivity to {host}:443",
            )

    def _check_docker_reachable(self) -> CheckResult:
        docker_host = os.environ.get("DOCKER_HOST", "")
        if not docker_host:
            return CheckResult("docker_reachable", CheckStatus.SKIP, "DOCKER_HOST not set")
        try:
            host = docker_host.replace("tcp://", "").split(":")[0]
            port = int(docker_host.split(":")[-1]) if ":" in docker_host else 2376
            with socket.create_connection((host, port), timeout=5):
                return CheckResult("docker_reachable", CheckStatus.OK, f"Docker reachable at {docker_host}")
        except Exception as e:
            return CheckResult("docker_reachable", CheckStatus.WARN, f"Docker unreachable: {e}")

    def _check_mcp_reachable(self) -> CheckResult:
        host = os.environ.get("FLOWCORE_MCP_HOST", "")
        if not host:
            return CheckResult("mcp_reachable", CheckStatus.SKIP, "FLOWCORE_MCP_HOST not set")
        try:
            port = int(os.environ.get("FLOWCORE_MCP_PORT", "8080"))
            with socket.create_connection((host, port), timeout=5):
                return CheckResult("mcp_reachable", CheckStatus.OK, f"MCP server reachable at {host}:{port}")
        except Exception as e:
            return CheckResult("mcp_reachable", CheckStatus.WARN, f"MCP server unreachable: {e}")

    # ── AI Bridges ───────────────────────────────────────────────────────────

    def _check_ollama(self) -> CheckResult:
        if is_available("ollama"):
            result = run(["ollama", "list"], timeout=10)
            if result.success:
                models = [line.split()[0] for line in result.stdout.strip().splitlines()[1:] if line.strip()]
                return CheckResult("ollama", CheckStatus.OK, f"ollama available, models: {models or ['none']}")
            return CheckResult("ollama", CheckStatus.WARN, "ollama installed but 'ollama list' failed")
        # No local ollama CLI (e.g. Ollama runs on the Windows host, reached from WSL2/Termux).
        # Use the same auto-discovery every other Ollama-touching code path uses instead of a
        # hardcoded 127.0.0.1:11434 — that would report "unreachable" on exactly this setup.
        try:
            endpoint = discover_ollama_endpoint()
            return CheckResult("ollama", CheckStatus.OK, f"ollama API reachable at {endpoint}")
        except OllamaDiscoveryError as e:
            return CheckResult(
                "ollama",
                CheckStatus.WARN,
                f"ollama not found: {e}",
                fix="curl -fsSL https://ollama.ai/install.sh | sh",
            )

    # ── Termux Runtime checks (Sprint 10) ────────────────────────────────────

    def _check_rsync(self) -> CheckResult:
        if is_available("rsync"):
            result = run(["rsync", "--version"], timeout=5)
            ver = result.stdout.splitlines()[0] if result.stdout else "rsync available"
            return CheckResult("rsync", CheckStatus.OK, ver)
        return CheckResult(
            "rsync",
            CheckStatus.WARN,
            "rsync not found — file sync/backup unavailable",
            fix="pkg install rsync",
        )

    def _check_cron(self) -> CheckResult:
        if is_available("crontab"):
            return CheckResult("cron", CheckStatus.OK, "crontab available")
        if is_available("termux-job-scheduler"):
            return CheckResult("cron", CheckStatus.OK, "termux-job-scheduler available")
        return CheckResult(
            "cron",
            CheckStatus.WARN,
            "No scheduler found (crontab / termux-job-scheduler)",
            fix="pkg install cronie  # or: pkg install termux-api",
        )

    def _check_termux_boot(self) -> CheckResult:
        if not os.environ.get("PREFIX"):
            return CheckResult("termux_boot", CheckStatus.SKIP, "Not in Termux")
        boot_dir = Path.home() / ".termux" / "boot"
        if boot_dir.exists():
            scripts = list(boot_dir.iterdir())
            if scripts:
                return CheckResult(
                    "termux_boot",
                    CheckStatus.OK,
                    f"Termux:Boot configured ({len(scripts)} script(s))",
                )
        if is_available("termux-wake-lock"):
            return CheckResult(
                "termux_boot",
                CheckStatus.WARN,
                "~/.termux/boot/ empty — FlowCore won't auto-start on reboot",
                fix="mkdir -p ~/.termux/boot && echo 'cd ~/FlowCore && sshd' > ~/.termux/boot/start.sh"
                " && chmod +x ~/.termux/boot/start.sh",
            )
        return CheckResult(
            "termux_boot",
            CheckStatus.SKIP,
            "Termux:Boot not installed (optional)",
        )

    def _check_daemon_state(self) -> CheckResult:
        try:
            from runtime.daemon import FlowCoreDaemon

            d = FlowCoreDaemon()
            if d.is_running():
                info = d.status()
                uptime = info.get("uptime", 0)
                return CheckResult(
                    "daemon_state",
                    CheckStatus.OK,
                    f"FlowCore daemon running (pid={info['pid']} uptime={uptime:.0f}s)",
                )
            return CheckResult(
                "daemon_state",
                CheckStatus.WARN,
                "FlowCore daemon not running",
                fix="python3 flowcore.py daemon start",
            )
        except Exception as e:
            return CheckResult("daemon_state", CheckStatus.SKIP, f"Daemon check skipped: {e}")

    # ── Runtime state ─────────────────────────────────────────────────────────

    def _check_runtime_json(self) -> CheckResult:
        runtime_json = Path.home() / ".flowcore" / "flowcore.runtime.json"
        if runtime_json.exists():
            import json

            try:
                data = json.loads(runtime_json.read_text())
                generated = data.get("generated_at", "unknown")
                return CheckResult("runtime_json", CheckStatus.OK, f"flowcore.runtime.json (generated {generated})")
            except Exception:
                return CheckResult(
                    "runtime_json",
                    CheckStatus.WARN,
                    "flowcore.runtime.json is corrupt",
                    fix='python3 -c "from runtime.kernel import RuntimeKernel; RuntimeKernel().boot()"',
                )
        return CheckResult(
            "runtime_json",
            CheckStatus.WARN,
            "flowcore.runtime.json not found — kernel has not booted",
            fix="python3 flowcore.py boot",
        )

    def _check_flowcore_config(self) -> CheckResult:
        root = Path(__file__).resolve().parent.parent
        cfg = root / "config" / "default.json"
        if cfg.exists():
            return CheckResult("flowcore_config", CheckStatus.OK, "config/default.json found")
        return CheckResult(
            "flowcore_config",
            CheckStatus.FAIL,
            "config/default.json missing",
            fix="Restore from repository or re-clone FlowCore",
        )

    # ── Telegram bot checks (Fase 3 / BLOCO 3) ───────────────────────────────

    def _check_telegram_dario_os(self) -> CheckResult:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            return CheckResult(
                "telegram_dario_os",
                CheckStatus.WARN,
                "TELEGRAM_BOT_TOKEN not set — Dario OS/SPC-X bot unconfigured",
                fix="Add TELEGRAM_BOT_TOKEN=<token> to ~/FlowCore/.env",
            )
        try:
            from runtime.telegram import _call
            result = _call("getMe", token, timeout=5)
            username = result.get("result", {}).get("username", "?")
            return CheckResult(
                "telegram_dario_os",
                CheckStatus.OK,
                f"Telegram — Dario OS/SPC-X: @{username} reachable",
            )
        except Exception as e:
            return CheckResult(
                "telegram_dario_os",
                CheckStatus.FAIL,
                f"Telegram — Dario OS/SPC-X: {e}",
                fix="Verify TELEGRAM_BOT_TOKEN and network connectivity",
            )

    def _check_telegram_b3(self) -> CheckResult:
        token = os.environ.get("TELEGRAM_BOT_TOKEN_B3")
        if not token:
            return CheckResult(
                "telegram_b3",
                CheckStatus.WARN,
                "TELEGRAM_BOT_TOKEN_B3 not set — B3/Ibovespa bot unconfigured",
                fix="Add TELEGRAM_BOT_TOKEN_B3=<token> to ~/FlowCore/.env",
            )
        try:
            from runtime.telegram import _call
            result = _call("getMe", token, timeout=5)
            username = result.get("result", {}).get("username", "?")
            return CheckResult(
                "telegram_b3",
                CheckStatus.OK,
                f"Telegram — B3/Ibovespa: @{username} reachable",
            )
        except Exception as e:
            return CheckResult(
                "telegram_b3",
                CheckStatus.FAIL,
                f"Telegram — B3/Ibovespa: {e}",
                fix="Verify TELEGRAM_BOT_TOKEN_B3 and network connectivity",
            )
