"""FlowCore Daily Brief Agent — runs the morning briefing pipeline on
demand (curva de juros, câmbio, regime, notícias, alertas).
"""
from __future__ import annotations

from typing import Any

from agents.base import BaseAgent


class DailyBriefAgent(BaseAgent):
    name = "daily_brief"
    description = "Gera o briefing diário de mercado (curva, câmbio, regime, notícias, alertas)"
    version = "0.1.0"

    async def run(self, context: dict | None = None) -> dict[str, Any]:
        from runtime.ai.brief_diario import build_brief
        use_llm = bool((context or {}).get("use_llm", False))
        return {"status": "ok", "data": build_brief(use_llm=use_llm)}
