"""Urgency Engine (Sprint 24, Layer 5 component).

Not every recommendation deserves immediate action. Urgency is a
deterministic function of the driver's own expected_impact label
(runtime/impact/scenarios.py's magnitude bucketing) and the driver's
statistical confidence -- both already computed upstream, combined here
with fixed, documented thresholds.
"""

from __future__ import annotations

__all__ = ["classify_urgency", "urgency_weight", "URGENCY_LEVELS"]

URGENCY_LEVELS = ("CRITICAL", "HIGH", "MEDIUM", "LOW")

_URGENCY_WEIGHT = {"CRITICAL": 1.0, "HIGH": 0.75, "MEDIUM": 0.5, "LOW": 0.25}


def classify_urgency(expected_impact_label: str, confidence_score: float, regime: str) -> str:
    """expected_impact_label is DriverImpact.expected_impact ("none" |
    "mild" | "moderate" | "strong"). A driver with no real regime data
    is never urgent, regardless of any other number."""
    if regime == "insufficient_data":
        return "LOW"
    if expected_impact_label == "strong" and confidence_score >= 0.8:
        return "CRITICAL"
    if expected_impact_label in ("strong", "moderate") and confidence_score >= 0.5:
        return "HIGH"
    if expected_impact_label in ("moderate", "mild") and confidence_score >= 0.3:
        return "MEDIUM"
    return "LOW"


def urgency_weight(urgency: str) -> float:
    return _URGENCY_WEIGHT.get(urgency, 0.25)
