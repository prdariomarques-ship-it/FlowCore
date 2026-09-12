#!/usr/bin/env python3
"""Signal Engine — sends a Telegram message for every REAL market alert
that fires (runtime/market_intelligence/alerts.py's evaluate_alerts(),
the same deterministic threshold engine the dashboard's own "Alertas"
card reads from). No invented trading signals, no backtested strategy —
just the existing, already-tested breach rules (VIX above 25, S&P/
Ibovespa daily drop past 3%, dollar above R$6, ...) turned into a real
Telegram message instead of only a row in the dashboard.

This is the process runtime/watchdog.py's KNOWN_BOTS["signal-engine"]
expects to find running (checked by process name, auto-restarted once
on failure). Runs forever, polling every --interval seconds; the alert
engine's own 24h-per-rule dedup (and its own 60s evaluation-sweep TTL
cache) already prevents duplicate/too-frequent sends, so this loop
doesn't need dedup logic of its own.

One-time install on a Termux device (the wrapper script itself stays
private/on-device only, same as every other bot under ~/.flowcore/bots
-- see runtime/watchdog.py's own docstring for why):

    mkdir -p ~/.flowcore/bots
    cat > ~/.flowcore/bots/signal-engine.sh <<'EOF'
    #!/data/data/com.termux/files/usr/bin/bash
    exec python3 "$HOME/FlowCore/scripts/signal_engine.py"
    EOF
    chmod +x ~/.flowcore/bots/signal-engine.sh

Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env (see
.env.example) -- the same bot/chat every other FlowCore Telegram
message already uses.

Manual test (single pass, real send if alerts are configured and any
rule is currently breached): python3 scripts/signal_engine.py --once
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_POLL_INTERVAL_SECONDS = 300  # 5 minutes -- comfortably above evaluate_alerts()'s own 60s sweep TTL

_SEVERITY_EMOJI = {"critical": "🔴", "warning": "🟡", "info": "🔵"}


def format_alert_message(alert: dict[str, Any]) -> str:
    """One real fired alert (see alerts.py's ALERT_DEFAULTS/evaluate_alerts)
    -> one Telegram HTML message. Never fabricates a value: whatever is
    missing from the payload is simply omitted, not guessed."""
    import html

    emoji = _SEVERITY_EMOJI.get(alert.get("severity", ""), "🔵")
    label = html.escape(str(alert.get("label", alert.get("rule", "?"))), quote=False)
    payload = alert.get("payload") or {}
    value = payload.get("value")
    lines = [f"{emoji} <b>SIGNAL ENGINE</b>", "", label]
    if isinstance(value, (int, float)):
        lines.append(f"Valor atual: {value:.2f}")
    delta = payload.get("delta_pct")
    if isinstance(delta, (int, float)):
        lines.append(f"Variação no dia: {delta:+.2f}%")
    return "\n".join(lines)


def check_and_send_signals() -> list[dict[str, Any]]:
    """One evaluation pass. Returns the alerts that were actually sent --
    empty when nothing new fired, when evaluate_alerts()'s own TTL cache
    skipped the sweep (called again too soon), or when Telegram isn't
    configured (logged, not raised, so the caller's loop keeps running)."""
    from runtime.market_intelligence.alerts import evaluate_alerts
    from runtime.telegram import TelegramError, TelegramNotConfiguredError, send_message

    fired = evaluate_alerts()
    sent: list[dict[str, Any]] = []
    for alert in fired:
        try:
            send_message(format_alert_message(alert))
            sent.append(alert)
        except TelegramNotConfiguredError as exc:
            print(f"[signal-engine] {exc}")
            break  # every other alert this pass would fail the same way
        except TelegramError as exc:
            print(f"[signal-engine] Failed to send alert '{alert.get('rule')}': {exc}")
    return sent


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Run a single evaluation pass and exit (manual testing)")
    parser.add_argument(
        "--interval", type=int, default=DEFAULT_POLL_INTERVAL_SECONDS,
        help=f"Seconds between evaluation passes (default: {DEFAULT_POLL_INTERVAL_SECONDS})",
    )
    args = parser.parse_args(argv)

    print(f"[signal-engine] Starting (interval={args.interval}s, once={args.once})...")
    while True:
        try:
            sent = check_and_send_signals()
            if sent:
                print(f"[signal-engine] Sent {len(sent)} alert(s): {[a.get('rule') for a in sent]}")
        except Exception as exc:  # noqa: BLE001 - a bad pass must not kill the supervised process
            print(f"[signal-engine] ERROR during evaluation pass: {exc}")
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
