"""FlowCore Intelligence Engine — interprets what a market/compliance event
means (Wealth Copilot MVP 2, phase 2).

ComplianceAgent answers "is this portfolio enquadrada?". MarketAgent
answers "what moved?". IntelligenceEngine sits between them and answers
"does this matter, and how much?" — classifying into exactly three
states:

  NEUTRAL      no relevant change, no action needed.
  RECALIBRATE  a relevant change occurred, but it doesn't invalidate the
               portfolio's thesis — a genuine desenquadramento (any
               CRITICAL ComplianceAgent violation) also lands here unless
               it can be tied to a specific market mover, since "the
               limit was breached" is not the same claim as "a new piece
               of information overturned a prior belief".
  OVERRIDE     a CRITICAL violation that a real market mover explains —
               the previous thesis actually needs to be revisited, not
               just monitored.

Market-to-portfolio correlation (MVP2 spec section 8) is intentionally
narrow for this MVP: one real, auditable rule (US Treasury 10Y -> the
target_allocation lines whose `benchmark` marks them duration-sensitive
— Prefixado, IMA-B 5+, and international fixed income/bonds), not a
statistical model and not a rule invented for every one of the nine
MarketAgent indicators. An indicator without a documented correlation
rule that still moves HIGH/MEDIUM gets a generic "monitorar" RECALIBRATE
instead of a fabricated sleeve-impact story.

Every classification is written to an append-only audit log
(~/.flowcore/intelligence_audit.jsonl) so "why was this OVERRIDE?" is
always answerable — see AuditRecord in agents/contracts.py.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agents.base import BaseAgent
from agents.contracts import AuditRecord, IntelligenceEvent

_DATA_DIR = Path.home() / ".flowcore"
_AUDIT_LOG = _DATA_DIR / "intelligence_audit.jsonl"

# The one real, documented market-to-sleeve correlation for this MVP.
# `sensitive_item_ids` are target_allocation ids whose `benchmark` field
# (in config/portfolio_moderate_1m.json, real data) marks them as
# duration-sensitive — Prefixado and IMA-B 5+ carry real interest-rate
# duration; international fixed income is priced off global (largely
# US-led) rates. CDI/Selic-indexed lines are deliberately excluded: they
# reprice with the floating rate, so a rate move does not hurt them the
# way it hurts a fixed-coupon or long-duration inflation bond.
_US10Y_SENSITIVE_ITEM_IDS = {
    "br_fixed_pre",
    "br_inflation_ima_b5",
    "br_inflation_ima_b5_plus",
    "us_treasury",
    "global_bonds",
    "corporate_bonds",
}
_US10Y_IMPACT = (
    "Ativos prefixados e de inflação longa (IMA-B 5+), além da renda fixa "
    "internacional, sofrem marcação a mercado negativa com juros mais altos."
)


class IntelligenceEngine(BaseAgent):
    name = "intelligence"
    description = "Classifica eventos de mercado/compliance em NEUTRAL, RECALIBRATE ou OVERRIDE"
    version = "0.1.0"

    async def run(self, context: dict | None = None) -> dict[str, Any]:
        context = context or {}
        market = context.get("market")
        if market is None:
            from agents.market_agent import MarketAgent

            market = (await MarketAgent().run())["data"]

        compliance = context.get("compliance")
        if compliance is None:
            office_id = context.get("office_id")
            if not office_id:
                raise ValueError(
                    "IntelligenceEngine.run() requires context['office_id'] (or a precomputed 'compliance')"
                )
            from agents.compliance_agent import ComplianceAgent

            compliance = (await ComplianceAgent().run({"office_id": office_id}))["data"]

        us10y_move = next((m for m in market.get("movements", []) if m["asset"] == "US Treasury 10Y"), None)
        us10y_high = bool(us10y_move and us10y_move.get("relevance") == "HIGH" and us10y_move.get("change") is not None)

        events: list[IntelligenceEvent] = []
        events.extend(self._market_events(market, us10y_move, us10y_high))
        events.extend(self._compliance_events(compliance, us10y_move, us10y_high))
        if not events:
            events.append(
                IntelligenceEvent(
                    status="NEUTRAL",
                    source="intelligence_engine",
                    reason="Nenhuma mudança relevante de mercado e nenhuma carteira desenquadrada.",
                )
            )

        for event in events:
            self._audit(event, context.get("office_id"))

        return {"status": "ok", "data": {"events": [e.to_dict() for e in events]}}

    # ── Market-driven events ─────────────────────────────────────────────────

    def _market_events(self, market: dict, us10y_move: dict | None, us10y_high: bool) -> list[IntelligenceEvent]:
        events: list[IntelligenceEvent] = []
        for m in market.get("movements", []):
            if m["relevance"] not in ("HIGH", "MEDIUM") or m.get("change") is None:
                continue
            unit = "p.p." if m["unit"] == "percentage_points" else "%"
            direction = "subiu" if m["change"] >= 0 else "caiu"
            if m["asset"] == "US Treasury 10Y" and us10y_high:
                events.append(
                    IntelligenceEvent(
                        status="RECALIBRATE",
                        source="intelligence_engine:us10y",
                        reason=(
                            f"US Treasury 10Y {direction} {abs(m['change']):.2f} p.p. "
                            "— sensibilidade de carteiras com duration mais longa aumenta, "
                            "mas isso sozinho não invalida a estratégia."
                        ),
                        suggested_action="Reavaliar duration.",
                        affected_assets=sorted(_US10Y_SENSITIVE_ITEM_IDS),
                    )
                )
                continue
            events.append(
                IntelligenceEvent(
                    status="RECALIBRATE",
                    source="intelligence_engine:generic",
                    reason=(
                        f"{m['asset']} {direction} {abs(m['change']):.2f}{unit} — variação {m['relevance'].lower()}."
                    ),
                    suggested_action="Monitorar posição.",
                )
            )
        return events

    # ── Compliance-driven events ─────────────────────────────────────────────

    def _compliance_events(
        self, compliance: dict, us10y_move: dict | None, us10y_high: bool
    ) -> list[IntelligenceEvent]:
        events: list[IntelligenceEvent] = []
        for portfolio in compliance.get("portfolios", []):
            for v in portfolio.get("violations", []):
                # WARNING is always a RECALIBRATE (falls to the generic branch
                # below). Only a CRITICAL violation is even eligible for
                # OVERRIDE, and only when a real market mover explains it.
                explained_by_us10y = v["severity"] == "CRITICAL" and us10y_high and "RENDA_FIXA_TOTAL" in v["type"]
                if explained_by_us10y:
                    events.append(
                        IntelligenceEvent(
                            status="OVERRIDE",
                            source="intelligence_engine:compliance+us10y",
                            reason=(
                                f"{v['client_name']}: {v['message']} — coincide com alta relevante "
                                "do US Treasury 10Y, não é apenas um desvio isolado."
                            ),
                            previous_thesis="Alocação de renda fixa estável dentro da banda definida.",
                            new_information=(
                                f"US Treasury 10Y {'subiu' if (us10y_move['change'] or 0) >= 0 else 'caiu'} "
                                f"{abs(us10y_move['change']):.2f} p.p., movimento classificado como HIGH."
                            ),
                            impact=_US10Y_IMPACT,
                            affected_assets=sorted(_US10Y_SENSITIVE_ITEM_IDS),
                            affected_portfolios=[v["client_id"]],
                            suggested_action="Investigar mudança de tese; preparar contato com cliente se confirmado.",
                        )
                    )
                    continue
                events.append(
                    IntelligenceEvent(
                        status="RECALIBRATE",
                        source="intelligence_engine:compliance",
                        reason=f"{v['client_name']}: {v['message']}",
                        suggested_action="Revisar carteira.",
                        affected_portfolios=[v["client_id"]],
                    )
                )
        return events

    # ── Audit trail ──────────────────────────────────────────────────────────

    def _audit(self, event: IntelligenceEvent, office_id: str | None) -> None:
        """One append-only log per office (fase 0: a shared global log
        would let one office's audit trail leak whichever office_id
        happened to run last into an eventual "why was this OVERRIDE?"
        endpoint for a different office)."""
        record = AuditRecord(
            timestamp=datetime.now(UTC).isoformat(),
            source=event.source,
            input={
                "office_id": office_id,
                "affected_assets": event.affected_assets,
                "affected_portfolios": event.affected_portfolios,
            },
            rule=event.source,
            classification=event.status,
            reason=event.reason,
            suggested_action=event.suggested_action,
        )
        log_path = _DATA_DIR / f"intelligence_audit_{office_id or 'unscoped'}.jsonl"
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except OSError:
            pass  # audit logging must never break the classification itself
