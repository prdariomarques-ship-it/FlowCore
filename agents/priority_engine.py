"""FlowCore Priority Engine — ranks events for the specialist's attention
(Wealth Copilot MVP 2, phase 3).

Consumes IntelligenceEngine's classified events and orders them so the
one thing that most needs a human's attention is first — never executes
anything, per spec section 17 (OBSERVAR -> ANALISAR -> EXPLICAR ->
PRIORIZAR -> SUGERIR, decision stays with the specialist).

Ranking rule (explicit, auditable — no scoring model):

  OVERRIDE               -> CRITICAL  (a prior thesis needs revisiting)
  RECALIBRATE, portfolio  -> HIGH      (already tied to a real
    affected                           desenquadramento, not just a
                                        market move)
  RECALIBRATE, market-only -> MEDIUM   (relevant move, no portfolio hit yet)
  NEUTRAL                 -> NEUTRAL

LOW exists in the PriorityLevel contract but is never produced by this
version — IntelligenceEngine already filters market movements down to
HIGH/MEDIUM relevance before turning them into events, so nothing this
engine sees is "barely worth mentioning". A future MarketAgent change
that also surfaces LOW-relevance movements would need a LOW branch here;
not invented ahead of that need.
"""
from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from agents.contracts import PriorityItem

_LEVEL_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "NEUTRAL": 4}


class PriorityEngine(BaseAgent):
    name = "priority"
    description = "Ordena eventos de IntelligenceEngine por prioridade de atenção"
    version = "0.1.0"

    async def run(self, context: dict | None = None) -> dict[str, Any]:
        context = context or {}
        events = context.get("events")
        if events is None:
            from agents.intelligence_engine import IntelligenceEngine
            events = (await IntelligenceEngine().run())["data"]["events"]

        items = [self._to_priority_item(e) for e in events]
        items.sort(key=lambda i: _LEVEL_ORDER[i.level])
        return {
            "status": "ok",
            "data": {
                "total": len(items),
                "by_level": {level: sum(1 for i in items if i.level == level) for level in _LEVEL_ORDER},
                "items": [i.to_dict() for i in items],
            },
        }

    @staticmethod
    def _to_priority_item(event: dict) -> PriorityItem:
        status = event["status"]
        affected_portfolios = event.get("affected_portfolios", [])
        if status == "OVERRIDE":
            level = "CRITICAL"
        elif status == "RECALIBRATE":
            level = "HIGH" if affected_portfolios else "MEDIUM"
        else:
            level = "NEUTRAL"
        title = {
            "OVERRIDE": "Revisão de tese recomendada",
            "RECALIBRATE": "Ajuste sugerido",
            "NEUTRAL": "Sem ação necessária",
        }[status]
        return PriorityItem(
            source="compliance" if affected_portfolios else "intelligence",
            level=level, title=title, reason=event["reason"],
            suggested_action=event.get("suggested_action") or "Nenhuma ação necessária.",
            affected_portfolios=affected_portfolios,
            affected_clients_count=len(affected_portfolios),
        )
