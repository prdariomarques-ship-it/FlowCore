"""Confidence Engine (Sprint 24, Layer 5 component).

Combines the originating driver's own statistical confidence
(DriverImpact.confidence_score, from Regime Engine's z-score magnitude --
see runtime/impact/scenarios.py's _confidence_score) with how much of the
portfolio is actually exposed (materiality) -- a decision touching 2% of
the portfolio should never carry the same confidence as one touching
60%, even when the underlying macro signal is identical. Reuses the
upstream confidence_score directly rather than recomputing it.

Deliberately does NOT attempt cross-dimension "conflicting signals"
detection (e.g. "Fed dovish BUT Treasury still rising" from the Sprint 24
spec's own example). With only 3 independent macro dimensions today
(liquidity, commodities, risk_sentiment) and no defined semantic
relationship between them anywhere in the codebase, any such detector
would be inventing relationships not grounded in real modeled knowledge
-- exactly the kind of fabrication this codebase's engines consistently
avoid (see runtime/macro_score's insufficient_data discipline). Flagged
here as a v2 extension point once more dimensions (inflation, growth,
credit) exist with actual defined interactions to check for agreement.
"""

from __future__ import annotations

__all__ = ["decision_confidence"]


def decision_confidence(
    driver_confidence_score: float, exposed_weight_pct: float, full_confidence_at_pct: float = 50.0
) -> float:
    """0..1. materiality_factor reaches 1.0 once exposed_weight_pct hits
    `full_confidence_at_pct` (default 50%) -- below that, confidence is
    scaled down linearly, since a technically-confident macro read still
    shouldn't produce a fully-confident *decision* if it barely touches
    the portfolio."""
    materiality_factor = min(1.0, exposed_weight_pct / full_confidence_at_pct)
    return round(driver_confidence_score * materiality_factor, 2)
