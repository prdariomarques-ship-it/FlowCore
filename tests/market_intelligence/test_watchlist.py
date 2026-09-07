"""Tests for runtime.market_intelligence.watchlist.snapshot() -- in
particular the PTAX fallback for USDBRL=X (see
runtime/observers/providers/ptax_provider.py's module docstring for why
"Câmbio" needed one and the other groups didn't).

fetch_quote and fetch_usdbrl_ptax are always mocked -- nothing here makes
a real network call.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.observers.base import ObserverError  # noqa: E402


class TestUsdbrlFallback:
    def test_falls_back_to_ptax_when_yfinance_fails(self):
        with patch(
            "runtime.market_intelligence.watchlist.fetch_quote",
            side_effect=ObserverError("USDBRL=X unavailable"),
        ), patch(
            "runtime.market_intelligence.watchlist.fetch_usdbrl_ptax",
            return_value={"symbol": "USDBRL=PTAX", "price": 5.20, "previous_close": 5.18},
        ):
            from runtime.market_intelligence.watchlist import snapshot

            result = snapshot("brasil")

        item = next(i for i in result["items"] if i["symbol"] == "USDBRL=X")
        assert item["status"] == "ok"
        assert item["level"] == 5.20
        assert item["delta_pct_1d"] == round((5.20 - 5.18) / 5.18 * 100, 2)

    def test_yfinance_success_never_touches_ptax(self):
        with patch(
            "runtime.market_intelligence.watchlist.fetch_quote",
            return_value={"symbol": "USDBRL=X", "price": 5.10, "previous_close": 5.05},
        ), patch("runtime.market_intelligence.watchlist.fetch_usdbrl_ptax") as ptax_mock:
            from runtime.market_intelligence.watchlist import snapshot

            result = snapshot("brasil")

        ptax_mock.assert_not_called()
        item = next(i for i in result["items"] if i["symbol"] == "USDBRL=X")
        assert item["level"] == 5.10

    def test_no_data_when_both_yfinance_and_ptax_fail(self):
        with patch(
            "runtime.market_intelligence.watchlist.fetch_quote",
            side_effect=ObserverError("USDBRL=X unavailable"),
        ), patch(
            "runtime.market_intelligence.watchlist.fetch_usdbrl_ptax",
            side_effect=ObserverError("PTAX also unavailable"),
        ):
            from runtime.market_intelligence.watchlist import snapshot

            result = snapshot("brasil")

        item = next(i for i in result["items"] if i["symbol"] == "USDBRL=X")
        assert item["status"] == "no_data"
        assert item["level"] is None

    def test_symbols_without_a_fallback_are_unaffected(self):
        with patch(
            "runtime.market_intelligence.watchlist.fetch_quote",
            side_effect=ObserverError("^BVSP unavailable"),
        ):
            from runtime.market_intelligence.watchlist import snapshot

            result = snapshot("brasil")

        item = next(i for i in result["items"] if i["symbol"] == "^BVSP")
        assert item["status"] == "no_data"
        assert item["level"] is None
