"""Canonical Narrative Engine output schema (Sprint 25)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

__all__ = ["NarrativeReport"]


@dataclass
class NarrativeReport:
    portfolio_id: int
    narrative: str
    source: str  # "llm" | "fallback"
    model: str | None
    fallback_reason: str | None
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "portfolio_id": self.portfolio_id,
            "narrative": self.narrative,
            "source": self.source,
            "model": self.model,
            "fallback_reason": self.fallback_reason,
            "generated_at": self.generated_at,
        }
