"""Tests for runtime.market_intelligence.* modules.

Live-data tests: they hit real yfinance endpoints (same pattern as
tests/observers/test_market_observers.py). Assertions are structural —
they never hardcode market levels, so they stay valid when prices move.
The module implementations guarantee every number comes from a real
quote; graceful degradation is covered by the watchlist mock sub-test.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

yfinance = pytest.importorskip("yfinance")

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def mocked_quotes():
    """Only used by the watchlist degradation sub-test below."""
    quotes = {
        "^BVSP": {"symbol": "^BVSP", "price": 166600.0, "previous_close": 166400.0},
        "USDBRL=X": {"symbol": "USDBRL=X", "price": 5.20, "previous_close": 5.15},
        "^IRX": {"symbol": "^IRX", "price": 3.70, "previous_close": 3.70},
        "^TNX": {"symbol": "^TNX", "price": 4.10, "previous_close": 4.05},
    }

    def quote(symbol, **_):
        try:
            return quotes[symbol]
        except KeyError:
            from runtime.observers.base import ObserverError

            raise ObserverError(f"No price data returned for {symbol}")

    with patch("runtime.market_intelligence.watchlist.fetch_quote", side_effect=quote):
        yield


class TestWatchlist:
    def test_list_watchlists(self):
        from runtime.market_intelligence.watchlist import list_watchlists

        names = list_watchlists()["watchlists"]
        assert "default" in names and "commodities" in names

    def test_snapshot_live_data(self):
        from runtime.market_intelligence.watchlist import snapshot

        data = snapshot("brasil")
        assert len(data["items"]) == 4
        ok_items = [i for i in data["items"] if i["status"] == "ok"]
        assert ok_items, "live brasil snapshot returned no data"
        for item in ok_items:
            assert item["level"] is not None and item["level"] > 0

    def test_snapshot_unknown_watchlist(self):
        from runtime.market_intelligence.watchlist import snapshot

        data = snapshot("inexistente")
        assert "error" in data and "available" in data

    def test_unknown_symbol_degrades_silently(self, mocked_quotes):
        from runtime.market_intelligence.watchlist import (
            DEFAULT_WATCHLISTS,
            snapshot,
        )

        DEFAULT_WATCHLISTS["broken"] = ["TICKER-INEXISTENTE"]
        try:
            data = snapshot("broken")
        finally:
            DEFAULT_WATCHLISTS.pop("broken")
        assert data["items"][0]["status"] == "no_data"
        assert data["items"][0]["level"] is None


class TestYieldCurve:
    def test_structure_with_live_data(self):
        from runtime.market_intelligence.yield_curve import build_yield_curve

        curve = build_yield_curve()
        assert curve.state in {
            "normal",
            "flat",
            "inverted",
            "steepening",
            "flattening",
            "insufficient_data",
        }
        d = curve.to_dict()
        assert "points" in d and "state" in d
        if curve.slope_10y_2y is not None:
            assert isinstance(d["slope_10y_2y_bps"], float)


class TestFx:
    def test_structure_with_live_data(self):
        from runtime.market_intelligence.fx_analysis import analyze_fx

        d = analyze_fx()
        assert "pairs" in d and "dxy_delta_pct_1d" in d
        valid_regimes = {"strengthening", "weakening", "neutral", "no_data"}
        assert all(p["usd_regime"] in valid_regimes for p in d["pairs"])


class TestAlerts:
    def test_list_and_evaluate(self):
        from runtime.market_intelligence.alerts import evaluate_alerts, list_alerts

        fired = evaluate_alerts()
        assert isinstance(fired, list)
        assert isinstance(list_alerts(), list)


class TestCalendar:
    def test_today_events_anchored(self):
        from datetime import UTC, datetime

        from runtime.market_intelligence.calendar import today_events

        now = datetime(2026, 8, 13, 10, 0, tzinfo=UTC)
        events = today_events(now)
        names = {e["event"] for e in events}
        assert "NYSE close" in names and "B3 close" in names


class TestBriefing:
    def test_briefing_live_data_lines(self):
        from runtime.market_intelligence.briefing import build_briefing

        d = build_briefing()
        assert "generated_at" in d and "lines" in d
        text = " ".join(d["lines"])
        assert "CURVA EUA" in text and "DÓLAR" in text
