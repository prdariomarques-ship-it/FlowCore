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
        with (
            patch(
                "runtime.market_intelligence.watchlist.fetch_quote",
                side_effect=ObserverError("USDBRL=X unavailable"),
            ),
            patch(
                "runtime.market_intelligence.watchlist.fetch_usdbrl_ptax",
                return_value={"symbol": "USDBRL=PTAX", "price": 5.20, "previous_close": 5.18},
            ),
        ):
            from runtime.market_intelligence.watchlist import snapshot

            result = snapshot("brasil")

        item = next(i for i in result["items"] if i["symbol"] == "USDBRL=X")
        assert item["status"] == "ok"
        assert item["level"] == 5.20
        assert item["delta_pct_1d"] == round((5.20 - 5.18) / 5.18 * 100, 2)

    def test_yfinance_success_never_touches_ptax(self):
        with (
            patch(
                "runtime.market_intelligence.watchlist.fetch_quote",
                return_value={"symbol": "USDBRL=X", "price": 5.10, "previous_close": 5.05},
            ),
            patch("runtime.market_intelligence.watchlist.fetch_usdbrl_ptax") as ptax_mock,
        ):
            from runtime.market_intelligence.watchlist import snapshot

            result = snapshot("brasil")

        ptax_mock.assert_not_called()
        item = next(i for i in result["items"] if i["symbol"] == "USDBRL=X")
        assert item["level"] == 5.10

    def test_no_data_when_both_yfinance_and_ptax_fail(self):
        with (
            patch(
                "runtime.market_intelligence.watchlist.fetch_quote",
                side_effect=ObserverError("USDBRL=X unavailable"),
            ),
            patch(
                "runtime.market_intelligence.watchlist.fetch_usdbrl_ptax",
                side_effect=ObserverError("PTAX also unavailable"),
            ),
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


class TestErrorSurfacing:
    """The real exception text used to be discarded entirely -- every
    failing symbol looked identical ("no_data"/"error") with no way to
    tell a timeout from an auth error from Yahoo blocking the network."""

    def test_no_data_item_carries_the_real_error_text(self):
        with patch(
            "runtime.market_intelligence.watchlist.fetch_quote",
            side_effect=ObserverError("Timed out fetching ^BVSP after 6.0s"),
        ):
            from runtime.market_intelligence.watchlist import snapshot

            result = snapshot("brasil")

        item = next(i for i in result["items"] if i["symbol"] == "^BVSP")
        assert item["error"] == "Timed out fetching ^BVSP after 6.0s"

    def test_generic_exception_error_text_is_also_captured(self):
        with patch(
            "runtime.market_intelligence.watchlist.fetch_quote",
            side_effect=RuntimeError("connection refused"),
        ):
            from runtime.market_intelligence.watchlist import snapshot

            result = snapshot("brasil")

        item = next(i for i in result["items"] if i["symbol"] == "^BVSP")
        assert item["status"] == "error"
        assert item["error"] == "connection refused"

    def test_ok_item_has_no_error(self):
        with patch(
            "runtime.market_intelligence.watchlist.fetch_quote",
            return_value={"symbol": "^BVSP", "price": 100.0, "previous_close": 99.0},
        ):
            from runtime.market_intelligence.watchlist import snapshot

            result = snapshot("brasil")

        item = next(i for i in result["items"] if i["symbol"] == "^BVSP")
        assert item["error"] is None


class TestFetchQuoteTimeoutBudget:
    """Regression guard: the original timeout=2.5/retries=0 was far
    tighter than yfinance_provider's own tuned defaults, and starved
    every quote on a real mobile network (Termux) -- see watchlist.py's
    fetch_item() for the full story. A later attempt at timeout=6.0/
    retries=1 with 16 concurrent workers *still* timed out on a real
    device (confirmed via the error field this same fase added) --
    likely from oversubscribing a constrained mobile connection with too
    many simultaneous sockets, not the per-call budget itself. Falls
    back fully to fetch_quote()'s own tuned defaults with less
    parallelism instead of a second guessed timeout value."""

    def test_fetch_quote_called_with_its_own_default_budget(self):
        with patch(
            "runtime.market_intelligence.watchlist.fetch_quote",
            return_value={"symbol": "^BVSP", "price": 100.0, "previous_close": 99.0},
        ) as mocked_fetch:
            from runtime.market_intelligence.watchlist import snapshot

            snapshot("brasil")

        for call in mocked_fetch.call_args_list:
            # No timeout/retries override -- fetch_quote()'s own defaults
            # (timeout=10.0, retries=2) apply.
            assert call.kwargs == {}
            assert call.args == (call.args[0],)
