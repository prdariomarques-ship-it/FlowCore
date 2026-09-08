"""FlowCore Notify Market Close Agent — the closing step of the "Fechamento
de Mercado" flow: reads the fechamento MarketCloseAgent just saved and sends
an Android notification with the actual result (a real headline), not a
generic "task completed" message.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agents.base import BaseAgent

_HISTORY_DIR = Path.home() / ".flowcore" / "market_close"


class NotifyMarketCloseAgent(BaseAgent):
    name = "notify_market_close"
    description = "Notifica no Android que o fechamento de mercado está pronto, com o resultado real"
    version = "0.1.0"

    async def run(self, context: dict | None = None) -> dict[str, Any]:
        from runtime.shell import is_available, run

        title = "📊 Fechamento de mercado pronto"
        message = self._latest_highlight() or "Fechamento de mercado disponível no FlowCore."

        if not is_available("termux-notification"):
            return {
                "status": "ok",
                "data": {"sent": False, "reason": "termux-notification indisponível", "message": message},
            }

        result = run(
            ["termux-notification", "--id", "9200", "--title", title, "--content", message],
            timeout=5,
        )
        return {"status": "ok", "data": {"sent": result.success, "title": title, "message": message}}

    @staticmethod
    def _latest_highlight() -> str | None:
        try:
            date_key = datetime.now(UTC).strftime("%Y-%m-%d")
            package = json.loads((_HISTORY_DIR / f"{date_key}.json").read_text())
            lines = package.get("raw_lines") or []
            return lines[0] if lines else None
        except Exception:
            return None
