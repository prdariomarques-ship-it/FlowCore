"""FlowCore Market Close Agent — runs "prepare o fechamento de mercado" on
demand: real data, client + Instagram texts, visual card, all saved to
~/.flowcore/market_close/<date>.*
"""
from __future__ import annotations

from typing import Any

from agents.base import BaseAgent


class MarketCloseAgent(BaseAgent):
    name = "market_close"
    description = "Prepara o fechamento de mercado: textos, card visual e histórico salvo"
    version = "0.1.0"

    async def run(self, context: dict | None = None) -> dict[str, Any]:
        from runtime.market_intelligence.market_close import build_market_close
        return {"status": "ok", "data": build_market_close()}
