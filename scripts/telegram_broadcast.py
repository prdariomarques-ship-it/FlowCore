#!/usr/bin/env python3
"""Scheduled Telegram broadcast job — Dario OS briefing + B3/Ibovespa summary.

Fires both /api/telegram/briefing (broad market, @dario_spcx_monitor_bot) and
/api/telegram/briefing-b3 (Ibovespa/USD-BRL focus, @dariozcodebot) against the
FlowCore API already running locally — this script is a thin scheduler, all
the actual composition/sending logic lives in runtime/telegram.py.

Self-gates on B3 pregão hours (seg-sex, 10h-18h BRT) so the cron entry can
just fire unconditionally every 30 min; outside that window it's a no-op.
Meant to run via crontab (scripts/install_telegram_cron.sh), same pattern as
scripts/ingest_observers.py.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

API_BASE = "http://127.0.0.1:8090"
B3_TZ = ZoneInfo("America/Sao_Paulo")
B3_OPEN_HOUR = 10
B3_CLOSE_HOUR = 18
STATUS_FILE = ROOT / "logs" / "telegram_broadcast.jsonl"


def _within_pregao(now: datetime) -> bool:
    return now.weekday() < 5 and B3_OPEN_HOUR <= now.hour < B3_CLOSE_HOUR


def _post(path: str, token: str) -> dict:
    resp = requests.post(f"{API_BASE}{path}", headers={"X-FlowCore-Token": token}, timeout=90)
    resp.raise_for_status()
    return resp.json()


def _log_status(entry: dict) -> None:
    STATUS_FILE.parent.mkdir(exist_ok=True)
    with open(STATUS_FILE, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def main() -> int:
    now = datetime.now(B3_TZ)
    if not _within_pregao(now):
        print(f"Fora do pregão B3 ({now:%Y-%m-%d %H:%M} BRT) — nada a fazer.")
        return 0

    token = os.environ.get("FLOWCORE_API_TOKEN", "")
    if not token:
        print("ERRO: FLOWCORE_API_TOKEN não configurado no .env.", file=sys.stderr)
        return 1

    results: dict[str, str] = {}
    for label, path in (("dario_os", "/api/telegram/briefing"), ("b3", "/api/telegram/briefing-b3")):
        try:
            _post(path, token)
            results[label] = "ok"
            print(f"{label}: enviado com sucesso")
        except requests.RequestException as e:
            results[label] = f"erro: {e}"
            print(f"{label}: FALHOU — {e}", file=sys.stderr)

    _log_status({"timestamp": now.isoformat(), **results})
    return 0 if all(v == "ok" for v in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
