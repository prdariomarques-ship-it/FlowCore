"""Priority Engine (Sprint 24, Layer 5 component).

priority_score = 0.30*macro_severity + 0.25*exposure_fraction +
                  0.20*impact_contribution + 0.15*confidence +
                  0.10*urgency_weight

All 5 terms are independently 0..1; weights sum to 1.0. This is the
single source of truth for the formula -- decision_queue.py only sorts
by the number this module produces, it never re-derives it.

Portfolio concentration deliberately does NOT feed into every decision's
priority score -- it only drives its own dedicated "reduce_concentration"
decision (via concentration_priority_score below) and the portfolio-level
Concentration/Protection sub-scores (runtime/decision/portfolio_score.py).
Folding a portfolio-wide concentration number into an unrelated
per-dimension decision (e.g. "increase inflation protection") would be
an arbitrary blend with no real causal relationship -- exactly the kind
of fabricated sophistication this codebase's engines avoid.
"""

from __future__ import annotations

from runtime.decision.urgency import urgency_weight

__all__ = ["macro_severity", "impact_contribution", "priority_score", "concentration_priority_score", "magnitude_label"]

_MAGNITUDE_THRESHOLDS = ((0.40, "HIGH"), (0.15, "MODERATE"), (0.0, "LOW"))


def macro_severity(regime_score: float | None, threshold: float) -> float:
    """0..1, how far beyond the elevated/depressed threshold the raw
    z-score sits. Distinct from DriverImpact.confidence_score (which
    reflects statistical trust in the reading, capped at 0.95) --
    severity purely measures magnitude, uncapped-feeling up to 1.0 at
    3x the threshold."""
    if regime_score is None:
        return 0.0
    return min(1.0, abs(regime_score) / (threshold * 3))


def impact_contribution(driver) -> float:
    """0..1, driver is a DriverImpact. The same
    exposed_weight*confidence shape runtime/impact/engine.py's
    _risk_score() uses for its negative component, applied per-driver
    instead of summed across drivers -- reused reasoning, not duplicated
    business logic."""
    if driver.direction == "negative":
        return min(1.0, driver.negative_weight_pct * driver.confidence_score / 100.0)
    if driver.direction == "positive":
        return min(1.0, driver.positive_weight_pct * driver.confidence_score / 100.0)
    return 0.0


def priority_score(driver, confidence: float, urgency: str, threshold: float = 1.0) -> float:
    severity = macro_severity(driver.regime_score, threshold)
    exposure_fraction = min(1.0, driver.exposed_weight_pct / 100.0)
    contribution = impact_contribution(driver)
    return round(
        0.30 * severity
        + 0.25 * exposure_fraction
        + 0.20 * contribution
        + 0.15 * confidence
        + 0.10 * urgency_weight(urgency),
        4,
    )


def concentration_priority_score(concentration, confidence: float, urgency: str) -> float:
    """Parallel formula for the portfolio-structural concentration
    decision, which has no single originating DriverImpact -- same 5
    weighted terms, HHI-derived severity/exposure/contribution instead
    of regime-derived ones."""
    severity = min(1.0, concentration.hhi / 10000.0)
    exposure_fraction = min(1.0, concentration.top_holding_weight_pct / 100.0)
    contribution = severity
    return round(
        0.30 * severity
        + 0.25 * exposure_fraction
        + 0.20 * contribution
        + 0.15 * confidence
        + 0.10 * urgency_weight(urgency),
        4,
    )


def magnitude_label(x: float) -> str:
    """Buckets a 0..1 contribution into NONE/LOW/MODERATE/HIGH -- used
    for Decision.estimated_risk_reduction (a fresh, confidence-weighted
    magnitude, deliberately distinct from DriverImpact.expected_impact,
    which only reflects raw exposure)."""
    if x <= 0:
        return "NONE"
    for threshold, label in _MAGNITUDE_THRESHOLDS:
        if x >= threshold:
            return label
    return "LOW"
