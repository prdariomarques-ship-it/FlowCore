"""Tests for runtime.portfolio.valuation.

yfinance is an optional dependency — same guard as test_asset_provider.py.
fetch_quote itself is mocked at the module boundary (its own retry/
timeout/cache/normalization behavior is covered in
tests/observers/test_yfinance_provider.py — not re-tested here).
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


def _holding(**overrides):
    holding = {"id": 1, "symbol": "AAPL", "quantity": 10.0, "average_cost": 150.0}
    holding.update(overrides)
    return holding


class TestValueHolding:
    def test_computes_market_value_and_gain(self):
        from runtime.portfolio.valuation import value_holding

        with patch(
            "runtime.portfolio.valuation.fetch_quote",
            return_value={"symbol": "AAPL", "price": 200.0, "previous_close": 195.0},
        ):
            result = value_holding(_holding())
        assert result["price"] == 200.0
        assert result["market_value"] == 2000.0
        assert result["cost_basis"] == 1500.0
        assert result["unrealized_gain"] == 500.0
        assert result["unrealized_gain_pct"] == pytest.approx(33.333, rel=1e-3)
        assert result["valuation_error"] is None

    def test_zero_cost_basis_gives_none_pct(self):
        from runtime.portfolio.valuation import value_holding

        with patch(
            "runtime.portfolio.valuation.fetch_quote",
            return_value={"symbol": "AAPL", "price": 200.0, "previous_close": 195.0},
        ):
            result = value_holding(_holding(average_cost=0.0))
        assert result["unrealized_gain_pct"] is None

    def test_propagates_fetch_failure(self):
        from runtime.observers.base import ObserverError
        from runtime.portfolio.valuation import value_holding

        with patch("runtime.portfolio.valuation.fetch_quote", side_effect=ObserverError("down")):
            with pytest.raises(ObserverError):
                value_holding(_holding())


class TestValueHoldings:
    def test_one_bad_symbol_does_not_break_the_batch(self):
        from runtime.observers.base import ObserverError
        from runtime.portfolio.valuation import value_holdings

        def fake_fetch(symbol):
            if symbol == "AAPL":
                return {"symbol": "AAPL", "price": 200.0, "previous_close": 195.0}
            raise ObserverError(f"no data for {symbol}")

        holdings = [_holding(symbol="AAPL"), _holding(id=2, symbol="BOGUS")]
        with patch("runtime.portfolio.valuation.fetch_quote", side_effect=fake_fetch):
            results = value_holdings(holdings)

        good, bad = results
        assert good["price"] == 200.0
        assert good["valuation_error"] is None
        assert bad["price"] is None
        assert bad["market_value"] is None
        assert bad["cost_basis"] == 1500.0  # still computable without a live price
        assert "no data for BOGUS" in bad["valuation_error"]

    def test_empty_list(self):
        from runtime.portfolio.valuation import value_holdings

        assert value_holdings([]) == []
