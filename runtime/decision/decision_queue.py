"""Decision Queue (Sprint 24, Layer 5 component).

Assembles and orders the final Decision Queue from already-scored
Decision candidates -- pure ranking logic, kept separate from how each
Decision's individual scores are computed (priority.py / confidence.py /
urgency.py) so ranking rules can evolve independently of scoring rules.
"""

from __future__ import annotations

from runtime.decision.models import Decision

__all__ = ["build_queue", "overall_priority", "overall_confidence"]


def build_queue(decisions: list[Decision]) -> list[Decision]:
    ordered = sorted(decisions, key=lambda d: d.priority_score, reverse=True)
    for i, d in enumerate(ordered, start=1):
        d.priority = i
    return ordered


def overall_priority(decisions: list[Decision]) -> str:
    """The top-ranked decision's urgency represents the portfolio's
    overall priority -- if the single most pressing thing is only
    MEDIUM, the portfolio as a whole isn't in a CRITICAL state."""
    if not decisions:
        return "NONE"
    return decisions[0].urgency


def overall_confidence(decisions: list[Decision]) -> float:
    """Priority-score-weighted average confidence -- decisions that rank
    higher (more severe, more exposed, more urgent) speak louder for the
    portfolio's overall confidence than a low-priority afterthought."""
    if not decisions:
        return 0.0
    weights = [d.priority_score for d in decisions]
    total = sum(weights)
    if not total:
        return round(sum(d.confidence for d in decisions) / len(decisions), 2)
    return round(sum(d.confidence * w for d, w in zip(decisions, weights, strict=True)) / total, 2)
