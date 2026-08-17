"""Tests for runtime.observers.market_observers.YFinanceObserver."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

yfinance = pytest.importorskip("yfinance")

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _make_observer(unit="price"):
    from runtime.observers.market_observers import YFinanceObserver

    return YFinanceObserver(
        source="vix", category="volatility", symbol="^VIX", event_name="volatility_change", unit=unit
    )


class TestObserve:
    def test_first_call_is_initial_observation(self):
        observer = _make_observer()
        with patch(
            "runtime.observers.market_observers.fetch_quote",
            return_value={"symbol": "^VIX", "price": 15.81, "previous_close": 16.5},
        ):
            events = observer.observe()
        assert len(events) == 1
        event = events[0]
        assert event.event == "initial_observation"
        assert event.source == "vix"
        assert event.category == "volatility"
        assert event.symbol == "^VIX"
        assert event.payload == {"value": 15.81, "previous_close": 16.5}
        assert "delta_pct" not in event.payload

    def test_second_call_computes_delta_pct(self):
        observer = _make_observer(unit="price")
        with patch(
            "runtime.observers.market_observers.fetch_quote",
            return_value={"symbol": "^VIX", "price": 10.0, "previous_close": 10.0},
        ):
            observer.observe()
        with patch(
            "runtime.observers.market_observers.fetch_quote",
            return_value={"symbol": "^VIX", "price": 15.0, "previous_close": 10.0},
        ):
            events = observer.observe()
        event = events[0]
        assert event.event == "volatility_change"
        assert event.payload["delta_pct"] == pytest.approx(50.0)

    def test_pct_unit_computes_delta_bps(self):
        from runtime.observers.market_observers import YFinanceObserver

        observer = YFinanceObserver(
            source="treasury", category="rates", symbol="^TNX", event_name="yield_change", unit="pct"
        )
        with patch(
            "runtime.observers.market_observers.fetch_quote",
            return_value={"symbol": "^TNX", "price": 4.40, "previous_close": 4.40},
        ):
            observer.observe()
        with patch(
            "runtime.observers.market_observers.fetch_quote",
            return_value={"symbol": "^TNX", "price": 4.58, "previous_close": 4.40},
        ):
            events = observer.observe()
        event = events[0]
        assert event.event == "yield_change"
        assert event.payload["delta_bps"] == pytest.approx(18.0, abs=0.01)
        assert "delta_pct" not in event.payload

    def test_provider_failure_propagates(self):
        from runtime.observers.base import ObserverError

        observer = _make_observer()
        with patch("runtime.observers.market_observers.fetch_quote", side_effect=ObserverError("down")):
            with pytest.raises(ObserverError):
                observer.observe()

    def test_severity_and_confidence_defaults(self):
        observer = _make_observer()
        with patch(
            "runtime.observers.market_observers.fetch_quote",
            return_value={"symbol": "^VIX", "price": 15.81, "previous_close": 16.5},
        ):
            events = observer.observe()
        assert events[0].severity == "info"
        assert events[0].confidence == 0.95


class TestDefaultObservers:
    def test_seven_sources(self):
        from runtime.observers.market_observers import default_yfinance_observers

        observers = default_yfinance_observers()
        sources = {o.source for o in observers}
        # The original 7 core sources are preserved (backward compatibility);
        # the set was expanded to BR/US/EU/Asia equities, rates, FX and
        # commodities — assert the superset property and a minimum count.
        assert {"treasury", "dollar", "vix", "oil", "gold", "usd_jpy", "treasury_30y"} <= sources
        assert len(sources) >= 25

    def test_usd_jpy_and_treasury_30y_are_real_yfinance_symbols(self):
        """Japan Duration Risk investigation: these two are the only
        components with a confirmed real data source (JGB 10Y, Japanese
        Treasury holdings, FIMA and capital flow have none -- see the
        investigation report). Confirms the symbols wired here are the
        exact ones verified live against Yahoo Finance, not placeholders."""
        from runtime.observers.market_observers import default_yfinance_observers

        by_source = {o.source: o for o in default_yfinance_observers()}
        assert len(by_source) >= 25
        assert by_source["usd_jpy"].symbol == "JPY=X"
        assert by_source["usd_jpy"].category == "fx"
        assert by_source["treasury_30y"].symbol == "^TYX"
        assert by_source["treasury_30y"].category == "rates"
        assert by_source["treasury_30y"].unit == "pct"
