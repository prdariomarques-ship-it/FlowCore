"""Canonical output schema for the Exposure Engine."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExposureBucket:
    label: str  # e.g. "Technology", or "Unclassified" when the grouping key is missing
    market_value: float
    weight_pct: float
    holding_count: int
    symbols: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "market_value": self.market_value,
            "weight_pct": self.weight_pct,
            "holding_count": self.holding_count,
            "symbols": self.symbols,
        }


@dataclass
class ExposureReport:
    dimension: str
    total_market_value: float
    buckets: list[ExposureBucket]
    unvalued_count: int
    computed_at: str

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "total_market_value": self.total_market_value,
            "buckets": [b.to_dict() for b in self.buckets],
            "unvalued_count": self.unvalued_count,
            "computed_at": self.computed_at,
        }


@dataclass
class ConcentrationReport:
    total_market_value: float
    top_holding_weight_pct: float
    top_5_weight_pct: float
    hhi: float
    holding_count: int
    unvalued_count: int
    computed_at: str

    def to_dict(self) -> dict:
        return {
            "total_market_value": self.total_market_value,
            "top_holding_weight_pct": self.top_holding_weight_pct,
            "top_5_weight_pct": self.top_5_weight_pct,
            "hhi": self.hhi,
            "holding_count": self.holding_count,
            "unvalued_count": self.unvalued_count,
            "computed_at": self.computed_at,
        }
