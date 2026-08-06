"""Tests for runtime.observers.providers.yfinance_provider.

yfinance is an optional (requirements-api.txt) dependency — needs the same
pytest.importorskip guard as tests/test_outlook.py/test_whatsapp.py.
Verify against a disposable core-only venv before committing.

Nothing here makes a real network call: yf.Ticker or the module's own
_fetch_once are always mocked.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

yfinance = pytest.importorskip("yfinance")

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _mock_ticker(last_price, previous_close):
    ticker = MagicMock()
    ticker.fast_info = {"last_price": last_price, "previous_close": previous_close}
    return ticker


@pytest.fixture(autouse=True)
def _clear_cache():
    from runtime.observers.providers import yfinance_provider as provider

    provider._cache.clear()
    yield
    provider._cache.clear()


class TestToFloat:
    def test_plain_number(self):
        from runtime.observers.providers.yfinance_provider import _to_float

        assert _to_float(15.81) == 15.81

    def test_none(self):
        from runtime.observers.providers.yfinance_provider import _to_float

        assert _to_float(None) is None

    def test_series_like_value(self):
        from runtime.observers.providers.yfinance_provider import _to_float

        class FakeSeries:
            def item(self):
                return 42.5

        assert _to_float(FakeSeries()) == 42.5

    def test_unparseable_returns_none(self):
        from runtime.observers.providers.yfinance_provider import _to_float

        assert _to_float("not-a-number") is None


class TestFetchQuote:
    def test_success(self):
        from runtime.observers.providers.yfinance_provider import fetch_quote

        with patch("runtime.observers.providers.yfinance_provider.yf.Ticker", return_value=_mock_ticker(15.81, 16.5)):
            result = fetch_quote("^VIX")
        assert result == {"symbol": "^VIX", "price": 15.81, "previous_close": 16.5}

    def test_camel_case_keys_supported(self):
        from runtime.observers.providers.yfinance_provider import fetch_quote

        ticker = MagicMock()
        ticker.fast_info = {"lastPrice": 79.28, "previousClose": 78.36}
        with patch("runtime.observers.providers.yfinance_provider.yf.Ticker", return_value=ticker):
            result = fetch_quote("BZ=F")
        assert result["price"] == 79.28

    def test_missing_price_raises(self):
        from runtime.observers.base import ObserverError
        from runtime.observers.providers.yfinance_provider import fetch_quote

        with patch("runtime.observers.providers.yfinance_provider.yf.Ticker", return_value=_mock_ticker(None, 16.5)):
            with pytest.raises(ObserverError, match="No price data"):
                fetch_quote("^VIX", retries=0)

    def test_empty_fast_info_raises(self):
        from runtime.observers.base import ObserverError
        from runtime.observers.providers.yfinance_provider import fetch_quote

        ticker = MagicMock()
        ticker.fast_info = {}
        with patch("runtime.observers.providers.yfinance_provider.yf.Ticker", return_value=ticker):
            with pytest.raises(ObserverError):
                fetch_quote("^VIX", retries=0)

    def test_caches_within_ttl(self):
        from runtime.observers.providers.yfinance_provider import fetch_quote

        with patch(
            "runtime.observers.providers.yfinance_provider.yf.Ticker", return_value=_mock_ticker(15.81, 16.5)
        ) as m:
            fetch_quote("^VIX")
            fetch_quote("^VIX")
        m.assert_called_once()

    def test_retry_then_succeed(self):
        from runtime.observers.providers.yfinance_provider import fetch_quote

        calls = {"n": 0}

        def flaky(symbol):
            calls["n"] += 1
            if calls["n"] < 2:
                raise RuntimeError("transient")
            return {"symbol": symbol, "price": 2.0, "previous_close": 1.9}

        with (
            patch("runtime.observers.providers.yfinance_provider._fetch_once", side_effect=flaky),
            patch("runtime.observers.providers.yfinance_provider._RETRY_BACKOFF_SECONDS", 0),
        ):
            result = fetch_quote("^VIX", timeout=5, retries=2)
        assert result["price"] == 2.0
        assert calls["n"] == 2

    def test_retry_exhausted_raises(self):
        from runtime.observers.base import ObserverError
        from runtime.observers.providers.yfinance_provider import fetch_quote

        with (
            patch("runtime.observers.providers.yfinance_provider._fetch_once", side_effect=RuntimeError("down")),
            patch("runtime.observers.providers.yfinance_provider._RETRY_BACKOFF_SECONDS", 0),
        ):
            with pytest.raises(ObserverError, match="Failed to fetch"):
                fetch_quote("^VIX", timeout=5, retries=2)

    def test_timeout_raises(self):
        from runtime.observers.base import ObserverError
        from runtime.observers.providers.yfinance_provider import fetch_quote

        def slow(symbol):
            time.sleep(1)
            return {"symbol": symbol, "price": 1.0, "previous_close": 1.0}

        with patch("runtime.observers.providers.yfinance_provider._fetch_once", side_effect=slow):
            with pytest.raises(ObserverError, match="Timed out"):
                fetch_quote("^VIX", timeout=0.05, retries=0)
