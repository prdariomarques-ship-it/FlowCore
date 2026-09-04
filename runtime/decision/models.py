"""Canonical Decision Engine output schema (Sprint 24, Layer 5).

Layer 5 sits after Product Mapping (Layer 4) in the SCPX pipeline:
Observer -> Macro Score -> Regime -> Exposure -> Portfolio Impact ->
Recommendation -> Product Mapping -> Decision. It never invents new
facts -- every field here is either copied straight from an upstream
engine's output or a documented, deterministic combination of them (see
runtime/decision/priority.py, confidence.py, urgency.py for the exact
formulas).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

__all__ = ["Decision", "SubScore", "PortfolioScore", "DecisionReport"]


@dataclass
class Decision:
    id: str  # == the originating Recommendation's action_key
    kind: str  # "risk" | "opportunity" -- negative/concentration vs. positive drivers
    dimension: str  # "" for portfolio-structural decisions (e.g. concentration)
    priority: int  # 1 = highest, assigned by decision_queue.build_queue()
    priority_score: float  # raw 0..1 score the rank above was derived from -- exposed for transparency
    urgency: str  # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
    confidence: float  # 0..1
    expected_impact: str  # "NONE" | "LOW" | "MODERATE" | "HIGH"
    # "NONE"|"LOW"|"MODERATE"|"HIGH" -- benefit if acted on (risk: reduction; opportunity: upside captured)
    estimated_risk_reduction: str
    action: str
    reason: str
    reason_chain: list[str] = field(default_factory=list)
    affected_holdings: list[str] = field(default_factory=list)
    affected_asset_classes: list[str] = field(default_factory=list)
    recommended_products: list[dict] = field(default_factory=list)
    computed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "dimension": self.dimension,
            "priority": self.priority,
            "priority_score": self.priority_score,
            "urgency": self.urgency,
            "confidence": self.confidence,
            "expected_impact": self.expected_impact,
            "estimated_risk_reduction": self.estimated_risk_reduction,
            "action": self.action,
            "reason": self.reason,
            "reason_chain": self.reason_chain,
            "affected_holdings": self.affected_holdings,
            "affected_asset_classes": self.affected_asset_classes,
            "recommended_products": self.recommended_products,
            "computed_at": self.computed_at,
        }


@dataclass
class SubScore:
    name: str
    score: float | None  # None when status == "insufficient_data" -- never a fabricated 0
    status: str  # "computed" | "insufficient_data"
    detail: str  # the exact formula/source used, for transparency

    def to_dict(self) -> dict:
        return {"name": self.name, "score": self.score, "status": self.status, "detail": self.detail}


@dataclass
class PortfolioScore:
    overall: float | None
    overall_status: str  # "computed" | "insufficient_data"
    sub_scores: list[SubScore]
    computed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "overall": self.overall,
            "overall_status": self.overall_status,
            "sub_scores": [s.to_dict() for s in self.sub_scores],
            "computed_at": self.computed_at,
        }


@dataclass
class DecisionReport:
    portfolio_id: int
    overall_priority: str  # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "NONE"
    overall_confidence: float
    decisions: list[Decision]
    portfolio_score: PortfolioScore
    top_risks: list[str]
    top_opportunities: list[str]
    unvalued_count: int
    computed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "portfolio_id": self.portfolio_id,
            "overall_priority": self.overall_priority,
            "overall_confidence": self.overall_confidence,
            "decisions": [d.to_dict() for d in self.decisions],
            "portfolio_score": self.portfolio_score.to_dict(),
            "top_risks": self.top_risks,
            "top_opportunities": self.top_opportunities,
            "unvalued_count": self.unvalued_count,
            "computed_at": self.computed_at,
        }
