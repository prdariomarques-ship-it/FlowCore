"""Tests for agents/market_agent.py (Wealth Copilot MVP 2, phase 1).

Mocks runtime.market_intelligence.watchlist.snapshot() so these are
deterministic and don't depend on live yfinance access — MarketAgent's
job is classifying whatever watchlist.py hands it, not fetching data
itself, so that's the right seam to mock at.
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

from agents.market_agent import MarketAgent
from config.market_thresholds import MARKET_THRESHOLDS


def _run(coro):
    return asyncio.run(coro)


def _fake_snapshot(items: dict[str, dict]) -> dict:
    """items: symbol -> {level, delta_pct_1d, status}"""
    return {"watchlist": "default", "items": [{"symbol": s, **v} for s, v in items.items()]}


class TestPercentIndicators:
    def test_small_move_is_low_relevance(self):
        # sp500 thresholds: high=1.2, medium=0.5
        items = _fake_snapshot({"^GSPC": {"level": 5000.0, "delta_pct_1d": 0.2, "status": "ok"}})
        with patch("runtime.market_intelligence.watchlist.snapshot", return_value=items):
            result = _run(MarketAgent().run())
        sp500 = next(m for m in result["data"]["movements"] if m["asset"] == "S&P 500")
        assert sp500["relevance"] == "LOW"
        assert sp500["change"] == 0.2
        assert sp500["source"] == "live"

    def test_move_above_high_threshold_is_high_relevance(self):
        items = _fake_snapshot({"^GSPC": {"level": 5000.0, "delta_pct_1d": 1.3, "status": "ok"}})
        with patch("runtime.market_intelligence.watchlist.snapshot", return_value=items):
            result = _run(MarketAgent().run())
        sp500 = next(m for m in result["data"]["movements"] if m["asset"] == "S&P 500")
        assert sp500["relevance"] == "HIGH"

    def test_negative_move_uses_absolute_value_for_relevance(self):
        items = _fake_snapshot({"^GSPC": {"level": 5000.0, "delta_pct_1d": -1.3, "status": "ok"}})
        with patch("runtime.market_intelligence.watchlist.snapshot", return_value=items):
            result = _run(MarketAgent().run())
        sp500 = next(m for m in result["data"]["movements"] if m["asset"] == "S&P 500")
        assert sp500["relevance"] == "HIGH"
        assert sp500["change"] == -1.3


class TestPercentagePointsIndicator:
    def test_us10y_change_is_computed_in_points_not_percent_of_percent(self):
        # current=4.22, a +2.837% day move on the price implies previous ~4.10
        # (4.22 / 1.02837 ~= 4.10) -> change ~= +0.12 percentage points, which
        # is exactly the mockup's "US Treasury 10Y +12 bps" example.
        current = 4.22
        previous = 4.10
        delta_pct = round((current - previous) / previous * 100, 4)  # ~2.9268
        items = _fake_snapshot({"^TNX": {"level": current, "delta_pct_1d": delta_pct, "status": "ok"}})
        with patch("runtime.market_intelligence.watchlist.snapshot", return_value=items):
            result = _run(MarketAgent().run())
        us10y = next(m for m in result["data"]["movements"] if m["asset"] == "US Treasury 10Y")
        assert us10y["unit"] == "percentage_points"
        assert abs(us10y["change"] - 0.12) < 0.01
        assert us10y["relevance"] == "HIGH"  # high threshold is 0.10 points


class TestMockIndicator:
    def test_di_is_explicitly_labeled_mock_never_blended_with_live(self):
        result = _run(MarketAgent().run())
        di = next(m for m in result["data"]["movements"] if m["asset"] == "DI Jan (futuro)")
        assert di["source"] == "MOCK"
        assert MARKET_THRESHOLDS["di"]["symbol"] is None  # no real feed exists


class TestMissingOrFailedSource:
    def test_symbol_absent_from_watchlist_response_reports_no_data_honestly(self):
        with patch("runtime.market_intelligence.watchlist.snapshot", return_value=_fake_snapshot({})):
            result = _run(MarketAgent().run())
        sp500 = next(m for m in result["data"]["movements"] if m["asset"] == "S&P 500")
        assert sp500["current_value"] is None
        assert sp500["change"] is None
        assert sp500["relevance"] == "LOW"
        assert sp500["source"] == "live"  # still "live" tier — absence isn't a MOCK substitute

    def test_symbol_with_error_status_reports_no_data(self):
        items = _fake_snapshot({"^GSPC": {"level": None, "delta_pct_1d": None, "status": "error"}})
        with patch("runtime.market_intelligence.watchlist.snapshot", return_value=items):
            result = _run(MarketAgent().run())
        sp500 = next(m for m in result["data"]["movements"] if m["asset"] == "S&P 500")
        assert sp500["current_value"] is None


class TestMarketStatus:
    def test_normal_when_everything_is_low_relevance(self):
        items = _fake_snapshot({s: {"level": 100.0, "delta_pct_1d": 0.01, "status": "ok"}
                                 for cfg in MARKET_THRESHOLDS.values() if (s := cfg["symbol"])})
        with patch("runtime.market_intelligence.watchlist.snapshot", return_value=items), \
             patch("agents.market_agent._DI_MOCK_CURRENT", 13.10):  # zero the mock's own move too
            result = _run(MarketAgent().run())
        assert result["data"]["market_status"] == "NORMAL"

    def test_alert_when_any_indicator_is_high(self):
        items = _fake_snapshot({"^GSPC": {"level": 5000.0, "delta_pct_1d": 5.0, "status": "ok"}})
        with patch("runtime.market_intelligence.watchlist.snapshot", return_value=items):
            result = _run(MarketAgent().run())
        assert result["data"]["market_status"] == "ALERT"


class TestAgentContract:
    def test_run_returns_full_market_snapshot_shape(self):
        result = _run(MarketAgent().run())
        assert result["status"] == "ok"
        data = result["data"]
        for key in ("timestamp", "market_status", "movements", "relevant_changes", "potential_impacts", "intelligence_events"):
            assert key in data
        assert len(data["movements"]) == len(MARKET_THRESHOLDS)

    def test_health_check(self):
        health = _run(MarketAgent().health_check())
        assert health["name"] == "market"
        assert health["status"] == "ok"
