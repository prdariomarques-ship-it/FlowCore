"""Tests for runtime.observers.event — the canonical MarketEvent schema."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestNewEvent:
    def test_fills_defaults(self):
        from runtime.observers.event import new_event

        event = new_event(source="vix", category="volatility", symbol="^VIX", event="volatility_change", payload={})
        assert event.severity == "info"
        assert event.confidence == 0.95
        assert event.metadata == {}
        assert event.id
        assert event.timestamp

    def test_unique_ids(self):
        from runtime.observers.event import new_event

        e1 = new_event(source="vix", category="volatility", symbol="^VIX", event="x", payload={})
        e2 = new_event(source="vix", category="volatility", symbol="^VIX", event="x", payload={})
        assert e1.id != e2.id

    def test_custom_severity_confidence_metadata(self):
        from runtime.observers.event import new_event

        event = new_event(
            source="vix",
            category="volatility",
            symbol="^VIX",
            event="x",
            payload={"value": 1},
            metadata={"provider": "yfinance"},
            severity="critical",
            confidence=0.5,
        )
        assert event.severity == "critical"
        assert event.confidence == 0.5
        assert event.metadata == {"provider": "yfinance"}


class TestToDict:
    def test_shape(self):
        from runtime.observers.event import MarketEvent

        event = MarketEvent(
            id="abc",
            timestamp="t",
            source="treasury",
            category="rates",
            symbol="^TNX",
            event="yield_change",
            severity="info",
            confidence=0.95,
            payload={"value": 4.58, "delta_bps": 18},
            metadata={"provider": "yfinance"},
        )
        assert event.to_dict() == {
            "id": "abc",
            "timestamp": "t",
            "source": "treasury",
            "category": "rates",
            "symbol": "^TNX",
            "event": "yield_change",
            "severity": "info",
            "confidence": 0.95,
            "payload": {"value": 4.58, "delta_bps": 18},
            "metadata": {"provider": "yfinance"},
        }
