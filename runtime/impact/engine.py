"""ImpactEngine — orchestrates Regime + Portfolio into an ImpactReport (Sprint 23).

Consumes RegimeEngine.classify_all() (already composes MacroScoreEngine,
which reads persisted MarketEvent history) and compute_concentration()
(Sprint 22, reused directly rather than recomputing HHI here) against a
portfolio's already-enriched holdings (service.list_holdings()'s output —
same input shape ExposureEngine consumes). No network calls of its own,
core-tier, no new dependency.

overall_impact / confidence / portfolio_risk_score are documented,
explainable heuristic composites (never a fabricated single "truth") —
see _aggregate_overall()/_risk_score()'s docstrings for the exact,
deterministic arithmetic behind each.
"""

from __future__ import annotations

from datetime import UTC, datetime

from runtime.exposure import compute_concentration
from runtime.impact.models import ImpactReport
from runtime.impact.recommendations import build_opportunities, build_recommendations
from runtime.impact.rules import RULES
from runtime.impact.scenarios import evaluate
from runtime.regime.engine import RegimeEngine

__all__ = ["ImpactEngine"]


def _aggregate_overall(drivers: list) -> tuple[str, float]:
    """Each contributing driver (real regime data + nonzero exposure)
    contributes signed_weight = direction_sign * (exposed_weight_pct/100)
    * confidence_score. Overall impact is the sign of the sum (a small
    epsilon band around zero counts as "neutral"); overall confidence is
    the exposed_weight_pct-weighted average of contributing drivers'
    confidence — drivers touching more of the portfolio speak louder.
    Insufficient/zero-exposure drivers never fabricate a contribution."""
    contributing = [d for d in drivers if d.regime != "insufficient_data" and d.exposed_weight_pct > 0]
    if not contributing:
        return "insufficient_data", 0.0

    net = sum(
        (1.0 if d.direction == "positive" else (-1.0 if d.direction == "negative" else 0.0))
        * (d.exposed_weight_pct / 100.0)
        * d.confidence_score
        for d in contributing
    )
    if abs(net) < 0.02:
        overall = "neutral"
    else:
        overall = "positive" if net > 0 else "negative"

    total_exposed = sum(d.exposed_weight_pct for d in contributing)
    confidence = round(sum(d.confidence_score * d.exposed_weight_pct for d in contributing) / total_exposed, 2)
    return overall, confidence


def _risk_score(drivers: list, concentration) -> float:
    """0-100 heuristic composite: 60% confidence-weighted negative macro
    exposure (capped at 100) + 40% concentration (HHI 0-10000 rescaled to
    0-100). Not a fabricated "true" risk metric - a documented, reviewable
    blend of two independently-computed, real signals."""
    negative_component = min(
        100.0, sum(d.negative_weight_pct * d.confidence_score for d in drivers if d.regime != "insufficient_data")
    )
    concentration_component = min(100.0, concentration.hhi / 100.0)
    score = 0.6 * negative_component + 0.4 * concentration_component
    return round(min(100.0, max(0.0, score)), 1)


class ImpactEngine:
    def __init__(self, regime_engine: RegimeEngine) -> None:
        self._regime_engine = regime_engine

    async def compute(self, portfolio_id: int, holdings: list[dict]) -> ImpactReport:
        signals = await self._regime_engine.classify_all()
        drivers = [evaluate(holdings, s) for s in signals if s.dimension in RULES]

        concentration = compute_concentration(holdings)
        overall_impact, confidence = _aggregate_overall(drivers)
        risk_score = _risk_score(drivers, concentration)
        affected_dimensions = [
            d.dimension
            for d in drivers
            if d.direction not in ("neutral", "insufficient_data") and d.exposed_weight_pct > 0
        ]
        recommendations = build_recommendations(holdings, drivers, concentration)
        opportunities = build_opportunities(drivers)
        unvalued_count = sum(1 for h in holdings if h.get("market_value") is None)

        return ImpactReport(
            portfolio_id=portfolio_id,
            overall_impact=overall_impact,
            confidence=confidence,
            portfolio_risk_score=risk_score,
            drivers=drivers,
            affected_dimensions=affected_dimensions,
            recommendations=recommendations,
            opportunities=opportunities,
            unvalued_count=unvalued_count,
            computed_at=datetime.now(UTC).isoformat(),
        )
