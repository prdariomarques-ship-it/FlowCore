"""Canonical DimensionScore — the Macro Score Engine's output schema."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DimensionScore:
    dimension: str
    status: str  # "scored" | "insufficient_data"
    score: float | None
    window_days: int
    z_scores: dict[str, float] = field(default_factory=dict)
    sample_counts: dict[str, int] = field(default_factory=dict)
    computed_at: str = ""

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "status": self.status,
            "score": self.score,
            "window_days": self.window_days,
            "z_scores": self.z_scores,
            "sample_counts": self.sample_counts,
            "computed_at": self.computed_at,
        }
