"""Deterministic recommendation/opportunity generation from DriverImpacts
+ portfolio concentration (Sprint 23) -- Layer 3 of the SCPX Impact
architecture (Regime -> Portfolio Impact -> Recommendation -> Product
Mapping).

Every recommendation carries a generic `action_key` ("reduce_duration",
"increase_usd_liquidity", ...) and human-readable text describing a
*category* of action -- never a specific ticker or fund. Turning
`action_key` into concrete, shelf-specific products is entirely
runtime/product_mapping/'s job (Layer 4); this module must never import
from or know about it, keeping the two layers swappable independently.

One action per macro dimension (a fixed, documented lookup — not
inferred), reused for every negative-direction driver (recommendations)
or positive-direction driver (opportunities), plus a concentration-based
recommendation reusing Sprint 22's compute_concentration() output
directly rather than recomputing HHI here.
"""

from __future__ import annotations

from runtime.exposure import ConcentrationReport
from runtime.impact.models import DriverImpact, Recommendation

__all__ = ["build_recommendations", "build_opportunities"]

# dimension -> (action_key, human-readable generic action)
_ACTION_FOR_NEGATIVE_DRIVER = {
    "liquidity": ("reduce_duration", "Reduzir duracao / aumentar liquidez de curto prazo"),
    "commodities": ("increase_inflation_protection", "Aumentar protecao contra inflacao"),
    "risk_sentiment": ("increase_usd_liquidity", "Aumentar liquidez em USD / reduzir exposicao a alto beta"),
}
_ACTION_FOR_POSITIVE_DRIVER = {
    "liquidity": ("increase_duration_exposure", "Considerar aumentar exposicao a duracao longa/crescimento"),
    "commodities": ("increase_commodities_exposure", "Considerar aumentar exposicao a protecao contra inflacao"),
    "risk_sentiment": ("increase_risk_exposure", "Considerar aumentar exposicao a ativos de maior risco/beta"),
}

_CONCENTRATION_HHI_THRESHOLD = 2500.0  # equivalent to <=4 equally-weighted holdings


def _driver_to_recommendation(driver: DriverImpact, action_map: dict[str, tuple[str, str]]) -> Recommendation:
    action_key, action = action_map.get(
        driver.dimension, ("review_exposure", f"Revisar exposicao a {driver.dimension}")
    )
    return Recommendation(
        action_key=action_key,
        action=action,
        reason=f"{driver.driver}. {driver.reason}",
        confidence=driver.confidence_score,
        affected_holdings=driver.affected_symbols,
        affected_asset_classes=driver.affected_asset_classes,
    )


def build_recommendations(
    holdings: list[dict], drivers: list[DriverImpact], concentration: ConcentrationReport
) -> list[Recommendation]:
    recs = [
        _driver_to_recommendation(d, _ACTION_FOR_NEGATIVE_DRIVER)
        for d in drivers
        if d.direction == "negative" and d.exposed_weight_pct > 0
    ]

    if concentration.hhi > _CONCENTRATION_HHI_THRESHOLD and concentration.holding_count > 0:
        valued = sorted(
            (h for h in holdings if h.get("market_value") is not None),
            key=lambda h: h["market_value"],
            reverse=True,
        )
        top_symbols = [h["symbol"] for h in valued[:5]]
        recs.append(
            Recommendation(
                action_key="reduce_concentration",
                action="Reduzir concentracao / aumentar diversificacao",
                reason=(
                    f"HHI atual de {concentration.hhi:.0f} (0-10000) indica concentracao elevada - "
                    f"a maior holding representa {concentration.top_holding_weight_pct:.1f}% do portfolio, "
                    f"e as 5 maiores somam {concentration.top_5_weight_pct:.1f}%."
                ),
                confidence=0.7,
                affected_holdings=top_symbols,
                affected_asset_classes=[],
            )
        )
    return recs


def build_opportunities(drivers: list[DriverImpact]) -> list[Recommendation]:
    return [
        _driver_to_recommendation(d, _ACTION_FOR_POSITIVE_DRIVER)
        for d in drivers
        if d.direction == "positive" and d.exposed_weight_pct > 0
    ]
