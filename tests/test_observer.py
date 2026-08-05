"""Tests for runtime.observer — SCPX Observer Engine (Sprint 18, Fase 1).

yfinance is an optional (requirements-api.txt) dependency, so this needs
the same pytest.importorskip guard as test_outlook.py/test_whatsapp.py —
verify against a disposable core-only venv before committing rather than
assuming.

yf.Ticker is mocked throughout — no real network/Yahoo Finance calls.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

yfinance = pytest.importorskip("yfinance")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _clear_cache():
    import runtime.observer as observer

    observer._cache.clear()
    yield
    observer._cache.clear()


def _mock_ticker(last_price, previous_close):
    fast_info = {"last_price": last_price, "previous_close": previous_close}
    ticker = MagicMock()
    ticker.fast_info = fast_info
    return ticker


class TestToFloat:
    def test_plain_number(self):
        from runtime.observer import _to_float

        assert _to_float(15.81) == 15.81

    def test_none(self):
        from runtime.observer import _to_float

        assert _to_float(None) is None

    def test_series_like_value(self):
        from runtime.observer import _to_float

        class FakeSeries:
            def item(self):
                return 42.5

        assert _to_float(FakeSeries()) == 42.5

    def test_unparseable_returns_none(self):
        from runtime.observer import _to_float

        assert _to_float("not-a-number") is None


class TestGetIndicator:
    def test_unknown_indicator_raises(self):
        from runtime.observer import ObserverError, get_indicator

        with pytest.raises(ObserverError, match="Unknown indicator"):
            get_indicator("bogus")

    def test_known_indicator_success(self):
        from runtime.observer import get_indicator

        with patch("runtime.observer.yf.Ticker", return_value=_mock_ticker(15.81, 16.50)):
            result = get_indicator("vix")
        assert result["name"] == "vix"
        assert result["symbol"] == "^VIX"
        assert result["price"] == 15.81
        assert result["previous_close"] == 16.50
        assert result["change_pct"] == pytest.approx(-4.181818, rel=1e-4)
        assert "checked_at" in result

    def test_zero_previous_close_yields_none_change(self):
        from runtime.observer import get_indicator

        with patch("runtime.observer.yf.Ticker", return_value=_mock_ticker(10.0, 0.0)):
            result = get_indicator("vix")
        assert result["change_pct"] is None

    def test_missing_price_raises(self):
        from runtime.observer import ObserverError, get_indicator

        with patch("runtime.observer.yf.Ticker", return_value=_mock_ticker(None, 16.5)):
            with pytest.raises(ObserverError, match="No price data"):
                get_indicator("vix")

    def test_network_failure_raises(self):
        from runtime.observer import ObserverError, get_indicator

        with patch("runtime.observer.yf.Ticker", side_effect=RuntimeError("connection refused")):
            with pytest.raises(ObserverError, match="Failed to fetch"):
                get_indicator("vix")

    def test_caches_within_ttl(self):
        from runtime.observer import get_indicator

        with patch("runtime.observer.yf.Ticker", return_value=_mock_ticker(15.81, 16.50)) as m:
            get_indicator("vix")
            get_indicator("vix")
        m.assert_called_once()

    def test_camel_case_keys_supported(self):
        from runtime.observer import get_indicator

        ticker = MagicMock()
        ticker.fast_info = {"lastPrice": 79.28, "previousClose": 78.36}
        with patch("runtime.observer.yf.Ticker", return_value=ticker):
            result = get_indicator("brent")
        assert result["price"] == 79.28


class TestCheckHealth:
    def test_success(self):
        from runtime.observer import check_health

        with patch("runtime.observer.yf.Ticker", return_value=_mock_ticker(15.81, 16.50)):
            result = check_health()
        assert result["name"] == "vix"

    def test_failure_propagates(self):
        from runtime.observer import ObserverError, check_health

        with patch("runtime.observer.yf.Ticker", side_effect=RuntimeError("timeout")):
            with pytest.raises(ObserverError):
                check_health()


class TestSymbols:
    def test_expected_indicators_present(self):
        from runtime.observer import SYMBOLS

        assert set(SYMBOLS) == {"treasury_10y", "usd_brl", "vix", "brent", "gold"}
