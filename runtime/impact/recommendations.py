"""Deterministic recommendation/opportunity generation from DriverImpacts
+ portfolio concentration (Sprint 23).

One action text per macro dimension (a fixed, documented lookup — not
inferred), reused for every negative-direction driver (recommendations)
or positive-direction driver (opportunities), plus a concentration-based
recommendation reusing Sprint 22's compute_concentration() output
directly rather than recomputing HHI here.
"""

from __future__ import annotations

from runtime.exposure import ConcentrationReport
from runtime.impact.models import DriverImpact, Recommendation

__all__ = ["build_recommendations", "build_opportunities"]

_ACTION_FOR_NEGATIVE_DRIVER = {
    "liquidity": "Reduzir duracao / aumentar caixa e ativos de taxa flutuante",
    "commodities": "Aumentar protecao contra inflacao (ouro, ativos indexados a IPCA)",
    "risk_sentiment": "Aumentar caixa em USD / reduzir exposicao a alto beta e small caps",
}
_ACTION_FOR_POSITIVE_DRIVER = {
    "liquidity": "Considerar aumentar exposicao a ativos de crescimento e duracao longa",
    "commodities": "Considerar aumentar exposicao a ouro/energia/commodities",
    "risk_sentiment": "Considerar aumentar exposicao a ativos de maior beta",
}

_CONCENTRATION_HHI_THRESHOLD = 2500.0  # equivalent to <=4 equally-weighted holdings


def _driver_to_recommendation(driver: DriverImpact, action_map: dict[str, str]) -> Recommendation:
    action = action_map.get(driver.dimension, f"Revisar exposicao ao dimensao {driver.dimension}")
    return Recommendation(
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
