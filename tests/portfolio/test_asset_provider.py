"""Tests for runtime.portfolio.asset_provider.fetch_asset_info.

yfinance is an optional (requirements-api.txt) dependency — needs the
same pytest.importorskip guard as tests/observers/test_yfinance_provider.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

yfinance = pytest.importorskip("yfinance")

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _mock_ticker(info: dict):
    ticker = MagicMock()
    ticker.info = info
    return ticker


class TestFetchAssetInfo:
    def test_equity(self):
        from runtime.portfolio.asset_provider import fetch_asset_info

        info = {
            "longName": "Apple Inc.",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "country": "United States",
            "currency": "USD",
            "quoteType": "EQUITY",
        }
        with patch("runtime.portfolio.asset_provider.yf.Ticker", return_value=_mock_ticker(info)):
            result = fetch_asset_info("AAPL")
        assert result == {
            "name": "Apple Inc.",
            "asset_class": "equity",
            "country": "United States",
            "currency": "USD",
            "sector": "Technology",
            "industry": "Consumer Electronics",
        }

    def test_etf_has_no_sector_industry(self):
        from runtime.portfolio.asset_provider import fetch_asset_info

        info = {
            "longName": "SPDR S&P 500 ETF Trust",
            "sector": None,
            "industry": None,
            "country": None,
            "currency": "USD",
            "quoteType": "ETF",
        }
        with patch("runtime.portfolio.asset_provider.yf.Ticker", return_value=_mock_ticker(info)):
            result = fetch_asset_info("SPY")
        assert result["asset_class"] == "etf"
        assert result["sector"] is None

    def test_falls_back_to_short_name(self):
        from runtime.portfolio.asset_provider import fetch_asset_info

        info = {"shortName": "Short Co", "quoteType": "EQUITY"}
        with patch("runtime.portfolio.asset_provider.yf.Ticker", return_value=_mock_ticker(info)):
            result = fetch_asset_info("SHRT")
        assert result["name"] == "Short Co"

    def test_unknown_symbol_raises(self):
        from runtime.portfolio.asset_provider import AssetProviderError, fetch_asset_info

        with patch("runtime.portfolio.asset_provider.yf.Ticker", return_value=_mock_ticker({})):
            with pytest.raises(AssetProviderError, match="Unknown symbol"):
                fetch_asset_info("ZZZZZZZZ")

    def test_unrecognized_quote_type_lowercased(self):
        from runtime.portfolio.asset_provider import fetch_asset_info

        info = {"longName": "Something", "quoteType": "OPTION"}
        with patch("runtime.portfolio.asset_provider.yf.Ticker", return_value=_mock_ticker(info)):
            result = fetch_asset_info("OPT")
        assert result["asset_class"] == "option"

    def test_network_failure_raises(self):
        from runtime.portfolio.asset_provider import AssetProviderError, fetch_asset_info

        with patch("runtime.portfolio.asset_provider.yf.Ticker", side_effect=RuntimeError("connection refused")):
            with pytest.raises(AssetProviderError, match="Failed to fetch"):
                fetch_asset_info("AAPL")
