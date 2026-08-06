"""Canonical MarketEvent — the one internal schema every Observer emits.

External APIs (yfinance today, others later) all have different shapes;
downstream components (Macro Score Engine, Regime Engine, ...) must never
need to know which provider or source produced an event, only this schema.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class MarketEvent:
    id: str
    timestamp: str
    source: str
    category: str
    symbol: str
    event: str
    severity: str
    confidence: float
    payload: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "source": self.source,
            "category": self.category,
            "symbol": self.symbol,
            "event": self.event,
            "severity": self.severity,
            "confidence": self.confidence,
            "payload": self.payload,
            "metadata": self.metadata,
        }


def new_event(
    *,
    source: str,
    category: str,
    symbol: str,
    event: str,
    payload: dict,
    metadata: dict | None = None,
    severity: str = "info",
    confidence: float = 0.95,
) -> MarketEvent:
    """Build a MarketEvent with sane defaults for id/timestamp.

    severity/confidence default to fixed placeholders in this phase —
    Observers only observe, they don't classify significance (that's a
    Macro Score / Regime Engine concern, future sprints).
    """
    return MarketEvent(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(UTC).isoformat(),
        source=source,
        category=category,
        symbol=symbol,
        event=event,
        severity=severity,
        confidence=confidence,
        payload=payload,
        metadata=metadata or {},
    )
