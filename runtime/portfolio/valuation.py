"""Live portfolio valuation.

Market value is never persisted (see storage/portfolio_repo.py's module
docstring) — it's computed fresh from a live quote every time a holding
is read. Reuses runtime.observers.providers.yfinance_provider.fetch_quote
directly (retry/timeout/cache already implemented there) instead of
duplicating fetch logic.
"""

from __future__ import annotations

from runtime.observers.base import ObserverError
from runtime.observers.providers.yfinance_provider import fetch_quote


def value_holding(holding: dict) -> dict:
    """Enrich a holding dict with price/market_value/cost_basis/unrealized
    gain. Raises ObserverError (propagated from fetch_quote) on failure —
    see value_holdings() for the batch version that degrades per-holding
    instead of failing the whole list."""
    quote = fetch_quote(holding["symbol"])
    price = quote["price"]
    quantity = holding["quantity"]
    cost_basis = holding["average_cost"] * quantity
    market_value = price * quantity
    unrealized_gain = market_value - cost_basis
    unrealized_gain_pct = (unrealized_gain / cost_basis * 100) if cost_basis else None
    return {
        **holding,
        "price": price,
        "market_value": market_value,
        "cost_basis": cost_basis,
        "unrealized_gain": unrealized_gain,
        "unrealized_gain_pct": unrealized_gain_pct,
        "valuation_error": None,
    }


def value_holdings(holdings: list[dict]) -> list[dict]:
    """Value every holding, one failure at a time — a bad quote for one
    symbol shouldn't hide the value of every other holding in the
    portfolio. A failed holding keeps its original fields plus
    valuation_error set and price/market_value/etc. as None."""
    results = []
    for holding in holdings:
        try:
            results.append(value_holding(holding))
        except ObserverError as e:
            results.append(
                {
                    **holding,
                    "price": None,
                    "market_value": None,
                    "cost_basis": holding["average_cost"] * holding["quantity"],
                    "unrealized_gain": None,
                    "unrealized_gain_pct": None,
                    "valuation_error": str(e),
                }
            )
    return results
