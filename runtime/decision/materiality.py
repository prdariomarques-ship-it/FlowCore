"""Materiality Engine (Sprint 24, Layer 5 component).

Filters out decisions whose expected portfolio impact is too small to
act on, so the Decision Queue stays signal, not noise. Layer 3
(runtime/impact/recommendations.py) already gates on exposed_weight_pct
> 0 (any real exposure at all) before a Recommendation exists; the
Decision Engine applies a stricter, separate threshold on top -- a
Recommendation means "there is something to consider," a Decision means
"this is worth queuing as an action."
"""

from __future__ import annotations

__all__ = ["MIN_EXPOSED_WEIGHT_PCT", "is_material"]

MIN_EXPOSED_WEIGHT_PCT = 5.0


def is_material(driver) -> bool:
    """driver is a runtime.impact.models.DriverImpact. A regime firing
    "elevated" over a dimension the portfolio has near-zero exposure to
    produces no decision -- there's nothing this specific portfolio can
    meaningfully act on."""
    if driver.regime == "insufficient_data":
        return False
    if driver.direction not in ("positive", "negative"):
        return False
    return driver.exposed_weight_pct >= MIN_EXPOSED_WEIGHT_PCT
