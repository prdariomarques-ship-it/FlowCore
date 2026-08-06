"""Canonical Impact Engine output schema (Sprint 23).

ImpactBucket mirrors runtime/exposure/bucket.py's ExposureBucket shape
(label/market_value/weight_pct/holding_count/symbols) but partitions
holdings differently — by which side of a macro driver rule they match
(positive/negative-exposed), not by a single classification value — so
it's a fresh dataclass, not a reuse of ExposureBucket.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

__all__ = ["ImpactBucket", "DriverImpact", "Recommendation", "ImpactReport"]


@dataclass
class ImpactBucket:
    label: str
    matched_direction: str  # "positive" | "negative"
    source: str  # "hard" | "soft"
    market_value: float
    weight_pct: float  # of total portfolio market value
    holding_count: int
    symbols: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "matched_direction": self.matched_direction,
            "source": self.source,
            "market_value": self.market_value,
            "weight_pct": self.weight_pct,
            "holding_count": self.holding_count,
            "symbols": self.symbols,
        }


@dataclass
class DriverImpact:
    dimension: str
    driver: str
    regime: str  # "elevated" | "depressed" | "neutral" | "insufficient_data"
    regime_score: float | None
    direction: str  # "positive" | "negative" | "neutral" | "insufficient_data"
    expected_impact: str  # "none" | "mild" | "moderate" | "strong"
    confidence_score: float  # 0..1
    confidence_label: str  # "low" | "medium" | "high"
    exposed_weight_pct: float  # positive_weight_pct + negative_weight_pct
    positive_weight_pct: float
    negative_weight_pct: float
    reason: str
    buckets: list[ImpactBucket] = field(default_factory=list)
    affected_symbols: list[str] = field(default_factory=list)
    affected_asset_classes: list[str] = field(default_factory=list)
    computed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "driver": self.driver,
            "regime": self.regime,
            "regime_score": self.regime_score,
            "direction": self.direction,
            "expected_impact": self.expected_impact,
            "confidence_score": self.confidence_score,
            "confidence_label": self.confidence_label,
            "exposed_weight_pct": self.exposed_weight_pct,
            "positive_weight_pct": self.positive_weight_pct,
            "negative_weight_pct": self.negative_weight_pct,
            "reason": self.reason,
            "buckets": [b.to_dict() for b in self.buckets],
            "affected_symbols": self.affected_symbols,
            "affected_asset_classes": self.affected_asset_classes,
            "computed_at": self.computed_at,
        }


@dataclass
class Recommendation:
    action: str
    reason: str
    confidence: float
    affected_holdings: list[str] = field(default_factory=list)
    affected_asset_classes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "reason": self.reason,
            "confidence": self.confidence,
            "affected_holdings": self.affected_holdings,
            "affected_asset_classes": self.affected_asset_classes,
        }


@dataclass
class ImpactReport:
    portfolio_id: int
    overall_impact: str  # "positive" | "negative" | "neutral" | "insufficient_data"
    confidence: float
    portfolio_risk_score: float  # 0..100
    drivers: list[DriverImpact]
    affected_dimensions: list[str]
    recommendations: list[Recommendation]
    opportunities: list[Recommendation]
    unvalued_count: int
    computed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "portfolio_id": self.portfolio_id,
            "overall_impact": self.overall_impact,
            "confidence": self.confidence,
            "portfolio_risk_score": self.portfolio_risk_score,
            "drivers": [d.to_dict() for d in self.drivers],
            "affected_dimensions": self.affected_dimensions,
            "recommendations": [r.to_dict() for r in self.recommendations],
            "opportunities": [r.to_dict() for r in self.opportunities],
            "unvalued_count": self.unvalued_count,
            "computed_at": self.computed_at,
        }
