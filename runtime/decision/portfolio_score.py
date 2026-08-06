"""Decision Readiness Score (Sprint 24, Layer 5 component).

8 named sub-scores (concentration, diversification, inflation_hedge,
currency_protection, duration, liquidity, macro_alignment, protection) +
an overall score, all deterministic, all reusing ExposureEngine /
ImpactEngine / compute_concentration output directly -- nothing here
recomputes HHI, sector grouping, or regime classification, it only
combines and labels numbers those engines already produced.

Sub-scores FlowCore has no real signal for yet (currency_protection,
liquidity -- no manually-tagged holdings and no dedicated regime
dimension to fall back on) return status="insufficient_data",
score=None -- never a fabricated number, same discipline as every other
SCPX engine. They are excluded from the overall average, not defaulted
to 0 (which would read as "bad" rather than "unknown").
"""

from __future__ import annotations

from datetime import UTC, datetime

from runtime.decision.models import PortfolioScore, SubScore

__all__ = ["compute_portfolio_score"]

_HIGH_TAG_VALUES = {"alta", "alto", "high"}


def _concentration_subscore(concentration) -> SubScore:
    if concentration.holding_count == 0:
        return SubScore("concentration", None, "insufficient_data", "Sem holdings valuadas.")
    score = round(max(0.0, 100.0 - min(100.0, concentration.hhi / 100.0)), 1)
    return SubScore("concentration", score, "computed", f"100 - HHI/100 (HHI={concentration.hhi:.0f}).")


def _diversification_subscore(exposure_engine, holdings) -> SubScore:
    report = exposure_engine.by_sector(holdings)
    if not report.buckets:
        return SubScore("diversification", None, "insufficient_data", "Sem holdings classificadas por setor.")
    n = len(report.buckets)
    score = round(min(100.0, n * (100.0 / 7)), 1)
    return SubScore(
        "diversification", score, "computed", f"{n} setor(es) distintos representados (referencia: 7+ = 100)."
    )


def _tag_weight_pct(exposure_engine, holdings, attribute: str) -> float:
    report = exposure_engine.by_attribute(holdings, attribute)
    return sum(b.weight_pct for b in report.buckets if str(b.label).strip().lower() in _HIGH_TAG_VALUES)


def _inflation_hedge_subscore(exposure_engine, holdings, commodities_driver) -> SubScore:
    tagged_pct = _tag_weight_pct(exposure_engine, holdings, "inflation_protection")
    if tagged_pct > 0:
        return SubScore(
            "inflation_hedge",
            round(tagged_pct, 1),
            "computed",
            f"{tagged_pct:.1f}% tagueado inflation_protection=alta.",
        )
    if commodities_driver is not None and commodities_driver.regime != "insufficient_data":
        pct = commodities_driver.positive_weight_pct
        return SubScore(
            "inflation_hedge",
            round(pct, 1),
            "computed",
            f"Sem tagging manual -- exposicao positiva do driver commodities ({pct:.1f}%).",
        )
    return SubScore(
        "inflation_hedge", None, "insufficient_data", "Sem tagging manual e sem regime de commodities disponivel."
    )


def _currency_protection_subscore(exposure_engine, holdings) -> SubScore:
    tagged_pct = _tag_weight_pct(exposure_engine, holdings, "currency_protection")
    if tagged_pct > 0:
        return SubScore(
            "currency_protection",
            round(tagged_pct, 1),
            "computed",
            f"{tagged_pct:.1f}% tagueado currency_protection=alta.",
        )
    return SubScore(
        "currency_protection",
        None,
        "insufficient_data",
        "Sem tagging manual -- FlowCore nao tem uma dimensao de regime cambial dedicada.",
    )


def _liquidity_subscore(exposure_engine, holdings) -> SubScore:
    tagged_pct = _tag_weight_pct(exposure_engine, holdings, "liquidity")
    if tagged_pct > 0:
        return SubScore("liquidity", round(tagged_pct, 1), "computed", f"{tagged_pct:.1f}% tagueado liquidity=alta.")
    return SubScore("liquidity", None, "insufficient_data", "Sem tagging manual de liquidez nas holdings.")


def _duration_subscore(liquidity_driver) -> SubScore:
    """Deliberately does NOT read the interest_rate_sensitivity tag
    directly -- unlike inflation_protection/currency_protection/
    liquidity, whose "alta" tag is unambiguously good regardless of
    regime, "alta" interest rate sensitivity is only bad *when yields
    are rising* -- that direction is already correctly resolved by
    runtime/impact/scenarios.py's regime-aware classification. Reusing
    the driver's positive_weight_pct avoids re-deriving that logic (and
    risking getting the sign backwards) here."""
    if liquidity_driver is None or liquidity_driver.regime == "insufficient_data":
        return SubScore("duration", None, "insufficient_data", "Regime de juros/liquidez ainda sem dados suficientes.")
    pct = liquidity_driver.positive_weight_pct
    return SubScore(
        "duration",
        round(pct, 1),
        "computed",
        f"Exposicao positiva do driver liquidity no regime atual ({liquidity_driver.regime}): {pct:.1f}%.",
    )


def _macro_alignment_subscore(impact_report) -> SubScore:
    score = round(max(0.0, 100.0 - impact_report.portfolio_risk_score), 1)
    return SubScore(
        "macro_alignment", score, "computed", f"100 - portfolio_risk_score ({impact_report.portfolio_risk_score:.1f})."
    )


def _protection_subscore(sub_scores: list[SubScore]) -> SubScore:
    relevant = [
        s
        for s in sub_scores
        if s.name in ("inflation_hedge", "currency_protection", "duration", "liquidity") and s.status == "computed"
    ]
    if not relevant:
        return SubScore("protection", None, "insufficient_data", "Nenhum componente de protecao disponivel ainda.")
    avg = round(sum(s.score for s in relevant) / len(relevant), 1)
    names = ", ".join(s.name for s in relevant)
    return SubScore("protection", avg, "computed", f"Media de {len(relevant)} componente(s) disponivel(is): {names}.")


def compute_portfolio_score(exposure_engine, holdings: list[dict], impact_report, concentration) -> PortfolioScore:
    liquidity_driver = next((d for d in impact_report.drivers if d.dimension == "liquidity"), None)
    commodities_driver = next((d for d in impact_report.drivers if d.dimension == "commodities"), None)

    sub_scores = [
        _concentration_subscore(concentration),
        _diversification_subscore(exposure_engine, holdings),
        _inflation_hedge_subscore(exposure_engine, holdings, commodities_driver),
        _currency_protection_subscore(exposure_engine, holdings),
        _duration_subscore(liquidity_driver),
        _liquidity_subscore(exposure_engine, holdings),
        _macro_alignment_subscore(impact_report),
    ]
    sub_scores.append(_protection_subscore(sub_scores))

    computed = [s for s in sub_scores if s.status == "computed"]
    if computed:
        overall = round(sum(s.score for s in computed) / len(computed), 1)
        overall_status = "computed"
    else:
        overall = None
        overall_status = "insufficient_data"

    return PortfolioScore(
        overall=overall,
        overall_status=overall_status,
        sub_scores=sub_scores,
        computed_at=datetime.now(UTC).isoformat(),
    )
