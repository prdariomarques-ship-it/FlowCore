"""Canonical RegimeSignal — the Regime Engine's output schema."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RegimeSignal:
    dimension: str
    regime: str  # "elevated" | "depressed" | "neutral" | "insufficient_data"
    score: float | None
    threshold: float
    computed_at: str

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "regime": self.regime,
            "score": self.score,
            "threshold": self.threshold,
            "computed_at": self.computed_at,
        }
