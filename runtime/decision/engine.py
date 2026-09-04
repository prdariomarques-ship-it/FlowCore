"""DecisionEngine -- Layer 5 orchestrator (Sprint 24).

Consumes ImpactEngine (Layer 2+3, already composes RegimeEngine +
compute_concentration + the Recommendation Engine), ExposureEngine
(Layer for sub-scores) and runtime/product_mapping/ (Layer 4) -- never
duplicates any of their computation, only combines and ranks it.

Iterates over ImpactReport.recommendations + .opportunities (already
gated by Layer 3's exposed_weight_pct > 0 / concentration-threshold
checks) as the base decision candidates, applies the Decision Engine's
own stricter materiality gate on top, scores and ranks what survives.
"""

from __future__ import annotations

from datetime import UTC, datetime

from runtime.decision import materiality, priority
from runtime.decision.confidence import decision_confidence
from runtime.decision.decision_queue import build_queue, overall_confidence, overall_priority
from runtime.decision.models import Decision, DecisionReport
from runtime.decision.portfolio_score import compute_portfolio_score
from runtime.decision.reason_chain import build_for_concentration, build_for_driver
from runtime.decision.urgency import classify_urgency
from runtime.exposure import ExposureEngine, compute_concentration
from runtime.impact import ImpactEngine
from runtime.product_mapping import DEFAULT_SHELF, map_action

_EXPECTED_IMPACT_MAP = {"none": "NONE", "mild": "LOW", "moderate": "MODERATE", "strong": "HIGH"}

__all__ = ["DecisionEngine"]


class DecisionEngine:
    def __init__(self, impact_engine: ImpactEngine, exposure_engine: ExposureEngine) -> None:
        self._impact_engine = impact_engine
        self._exposure_engine = exposure_engine

    async def compute(self, portfolio_id: int, holdings: list[dict], shelf: str = DEFAULT_SHELF) -> DecisionReport:
        impact_report = await self._impact_engine.compute(portfolio_id, holdings)
        concentration = compute_concentration(holdings)

        drivers_by_dimension = {d.dimension: d for d in impact_report.drivers}
        decisions: list[Decision] = []

        for rec in list(impact_report.recommendations) + list(impact_report.opportunities):
            if rec.dimension:
                driver = drivers_by_dimension.get(rec.dimension)
                if driver is None or not materiality.is_material(driver):
                    continue
                confidence = decision_confidence(driver.confidence_score, driver.exposed_weight_pct)
                urgency = classify_urgency(driver.expected_impact, driver.confidence_score, driver.regime)
                score = priority.priority_score(driver, confidence, urgency)
                reason_chain = build_for_driver(driver, rec)
                expected_impact = _EXPECTED_IMPACT_MAP.get(driver.expected_impact, "NONE")
                risk_reduction = priority.magnitude_label(priority.impact_contribution(driver))
                kind = "risk" if driver.direction == "negative" else "opportunity"
            else:
                confidence = decision_confidence(rec.confidence, concentration.top_holding_weight_pct)
                urgency = classify_urgency("moderate", confidence, "elevated")
                score = priority.concentration_priority_score(concentration, confidence, urgency)
                reason_chain = build_for_concentration(concentration, rec)
                expected_impact = "MODERATE"
                risk_reduction = priority.magnitude_label(min(1.0, concentration.hhi / 10000.0))
                kind = "risk"

            decisions.append(
                Decision(
                    id=rec.action_key,
                    kind=kind,
                    dimension=rec.dimension,
                    priority=0,  # assigned by build_queue()
                    priority_score=score,
                    urgency=urgency,
                    confidence=confidence,
                    expected_impact=expected_impact,
                    estimated_risk_reduction=risk_reduction,
                    action=rec.action,
                    reason=rec.reason,
                    reason_chain=reason_chain,
                    affected_holdings=rec.affected_holdings,
                    affected_asset_classes=rec.affected_asset_classes,
                    recommended_products=map_action(rec.action_key, shelf),
                )
            )

        decisions = build_queue(decisions)
        top_risks = [d.action for d in decisions if d.kind == "risk"][:3]
        top_opportunities = [d.action for d in decisions if d.kind == "opportunity"][:3]

        portfolio_score = compute_portfolio_score(self._exposure_engine, holdings, impact_report, concentration)

        return DecisionReport(
            portfolio_id=portfolio_id,
            overall_priority=overall_priority(decisions),
            overall_confidence=overall_confidence(decisions),
            decisions=decisions,
            portfolio_score=portfolio_score,
            top_risks=top_risks,
            top_opportunities=top_opportunities,
            unvalued_count=impact_report.unvalued_count,
            computed_at=datetime.now(UTC).isoformat(),
        )
