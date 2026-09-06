"""Typed data contracts shared by MarketAgent, IntelligenceEngine, and
PriorityEngine (FlowCore Wealth Copilot, MVP 2).

Plain dataclasses, matching the style already used for structured agent
output in this codebase (see runtime/market_intelligence/watchlist.py's
WatchlistItem) rather than introducing Pydantic here — Pydantic in this
project is reserved for FastAPI request bodies (api/dashboard_routes.py),
not for internal agent-to-agent payloads.

Every `to_dict()` omits fields that don't apply to the current variant
(e.g. an OVERRIDE-only field on a NEUTRAL event) instead of emitting
nulls for shapes that were never meant to have them — this keeps the
JSON honest about what was actually computed, the same principle
ComplianceAgent already applies (SEM_POSICAO_ATUAL / SEM_REGRAS_DEFINIDAS
instead of a guessed value).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Relevance = Literal["HIGH", "MEDIUM", "LOW"]
MarketStatus = Literal["NORMAL", "ATTENTION", "ALERT"]
IntelligenceStatus = Literal["NEUTRAL", "RECALIBRATE", "OVERRIDE"]
PriorityLevel = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "NEUTRAL"]


# ── MarketAgent ──────────────────────────────────────────────────────────────

@dataclass
class MarketMovement:
    """One asset's observed move against its previous close.

    `source` is always explicit: "live" when the value came from
    watchlist.snapshot() (yfinance), "MOCK" only as a fallback when the
    live source is unavailable — never silently blended, so a caller can
    always tell real data from a placeholder.
    """
    asset: str
    previous_value: float | None
    current_value: float | None
    change: float | None
    unit: Literal["percent", "percentage_points"]
    relevance: Relevance
    source: Literal["live", "MOCK"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset, "previous_value": self.previous_value,
            "current_value": self.current_value, "change": self.change,
            "unit": self.unit, "relevance": self.relevance, "source": self.source,
        }


@dataclass
class MarketSnapshot:
    timestamp: str
    market_status: MarketStatus
    movements: list[MarketMovement] = field(default_factory=list)
    relevant_changes: list[str] = field(default_factory=list)
    potential_impacts: list[str] = field(default_factory=list)
    # Populated by IntelligenceEngine when it processes this snapshot, not
    # by MarketAgent itself — kept here only as the output slot the two
    # agents share, per the "MarketAgent -> Market Intelligence ->
    # IntelligenceEngine" pipeline in the spec.
    intelligence_events: list["IntelligenceEvent"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp, "market_status": self.market_status,
            "movements": [m.to_dict() for m in self.movements],
            "relevant_changes": self.relevant_changes,
            "potential_impacts": self.potential_impacts,
            "intelligence_events": [e.to_dict() for e in self.intelligence_events],
        }


# ── IntelligenceEngine ───────────────────────────────────────────────────────

@dataclass
class IntelligenceEvent:
    """A single classified event: NEUTRAL, RECALIBRATE, or OVERRIDE.

    Fields beyond `status`/`reason` are populated according to which
    status this is — see to_dict(), which emits only what applies:
      NEUTRAL       -> status, reason
      RECALIBRATE   -> status, reason, suggested_action
      OVERRIDE      -> status, previous_thesis, new_information, impact,
                       affected_assets, affected_portfolios, suggested_action
    Never fabricate a value for a field that doesn't apply to the status —
    leave it None and let to_dict() drop it.
    """
    status: IntelligenceStatus
    reason: str
    suggested_action: str | None = None
    previous_thesis: str | None = None
    new_information: str | None = None
    impact: str | None = None
    affected_assets: list[str] = field(default_factory=list)
    affected_portfolios: list[str] = field(default_factory=list)
    source: str = ""  # which agent/rule produced this (for the audit trail)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"status": self.status, "reason": self.reason}
        if self.status == "RECALIBRATE":
            out["suggested_action"] = self.suggested_action
        elif self.status == "OVERRIDE":
            out.update({
                "previous_thesis": self.previous_thesis,
                "new_information": self.new_information,
                "impact": self.impact,
                "affected_assets": self.affected_assets,
                "affected_portfolios": self.affected_portfolios,
                "suggested_action": self.suggested_action,
            })
        return out


@dataclass
class AuditRecord:
    """One traceable IntelligenceEngine decision (spec section 15).

    Append-only by design — this is a decision log, not mutable state.
    """
    timestamp: str
    source: str
    input: dict[str, Any]
    rule: str
    classification: IntelligenceStatus
    reason: str
    suggested_action: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp, "source": self.source, "input": self.input,
            "rule": self.rule, "classification": self.classification,
            "reason": self.reason, "suggested_action": self.suggested_action,
        }


# ── PriorityEngine ───────────────────────────────────────────────────────────

@dataclass
class PriorityItem:
    """One prioritized occurrence — a ComplianceAgent violation or an
    IntelligenceEvent, ranked for the specialist's attention."""
    source: Literal["compliance", "intelligence"]
    level: PriorityLevel
    title: str
    reason: str
    suggested_action: str
    affected_portfolios: list[str] = field(default_factory=list)
    affected_clients_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source, "level": self.level, "title": self.title,
            "reason": self.reason, "suggested_action": self.suggested_action,
            "affected_portfolios": self.affected_portfolios,
            "affected_clients_count": self.affected_clients_count,
        }
