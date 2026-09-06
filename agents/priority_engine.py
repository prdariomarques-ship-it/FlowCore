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
            office_id = context.get("office_id")
            if not office_id:
                raise ValueError("PriorityEngine.run() requires context['office_id'] (or precomputed 'events')")
            from agents.intelligence_engine import IntelligenceEngine
            events = (await IntelligenceEngine().run({"office_id": office_id}))["data"]["events"]

        items = [self._to_priority_item(e) for e in events]
        items.sort(key=lambda i: _LEVEL_ORDER[i.level])
        return {
            "status": "ok",
            "data": {
                "total": len(items),
                "by_level": {level: sum(1 for i in items if i.level == level) for level in _LEVEL_ORDER},
                "items": [i.to_dict() for i in items],
                "by_client": await self._group_by_client(items, context.get("office_id")),
            },
        }

    # ── Per-client consolidation ────────────────────────────────────────────
    # A flat priority feed makes an advisor scan every row for "is this
    # about the same client as that other row?". Consolidating by client
    # answers the more useful question directly: which clients need
    # attention today, worst issue first — same items, no new data
    # invented, just grouped by the affected_portfolios each item already
    # carries. Items with no affected_portfolios (a market move not tied
    # to any specific client) are left out of this grouping on purpose —
    # they have nowhere honest to be filed under.

    async def _group_by_client(self, items: list[PriorityItem], office_id: str | None) -> list[dict[str, Any]]:
        grouped: dict[str, list[PriorityItem]] = {}
        for item in items:
            for client_id in item.affected_portfolios:
                grouped.setdefault(client_id, []).append(item)
        if not grouped:
            return []

        client_records: dict[str, dict[str, Any]] = {}
        if office_id:
            from storage.client_repo import ClientRepository
            client_records = {c["id"]: c for c in await ClientRepository().list_clients(office_id)}
            # A ComplianceAgent-evaluated "portfolio" can be the office's
            # own reference policy, not a real client (see
            # api/dashboard_routes.py's /api/alerts is_client flag for the
            # same distinction) — drop it here rather than showing a
            # client card the advisor can't actually open or contact.
            grouped = {cid: its for cid, its in grouped.items() if cid in client_records}

        entries = []
        for client_id, client_items in grouped.items():
            client_items = sorted(client_items, key=lambda i: _LEVEL_ORDER[i.level])
            record = client_records.get(client_id)
            entries.append({
                "client_id": client_id,
                # Falls back to the raw id only when there's no office_id to
                # resolve a real name against (e.g. a caller testing with
                # precomputed events directly) — never a guessed display name.
                "client_name": record["name"] if record else client_id,
                "is_demo": record["is_demo"] if record else None,
                "worst_level": client_items[0].level,
                "issues_count": len(client_items),
                "items": [i.to_dict() for i in client_items],
            })
        entries.sort(key=lambda e: (_LEVEL_ORDER[e["worst_level"]], -e["issues_count"], e["client_name"]))
        return entries

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
