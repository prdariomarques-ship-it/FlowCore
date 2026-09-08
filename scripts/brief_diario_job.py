#!/usr/bin/env python3
"""Standalone job: build morning brief and send to Telegram.

Scheduled via crontab at 07:30 BRT (10:30 UTC) on weekdays.
Safe to run manually: python3 ~/FlowCore/scripts/brief_diario_job.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from runtime.ai.brief_diario import build_brief, send_brief_to_telegram

    print("[brief] Building morning brief...")
    try:
        brief = build_brief(use_llm=True)
    except Exception as exc:
        print(f"[brief] ERROR building brief: {exc}")
        return 1

    sections_ok = sum(1 for s in brief["sections"].values() if s.get("ok"))
    sections_total = len(brief["sections"])
    print(f"[brief] Sections: {sections_ok}/{sections_total} OK")
    if brief.get("llm_error"):
        print(f"[brief] LLM polish skipped: {brief['llm_error']}")
    elif brief.get("llm_polish"):
        print("[brief] LLM polish applied.")

    print("[brief] Sending to Telegram...")
    sent = send_brief_to_telegram(brief)
    if sent:
        print("[brief] Sent successfully.")
    else:
        print("[brief] Telegram send failed (check TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID).")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
