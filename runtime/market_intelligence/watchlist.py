"""User-defined symbol watchlists — real data only via yfinance.

Watchlists are names mapping to lists of Yahoo Finance tickers. The
default watchlist covers the core market set already validated against
live yfinance (see runtime/observers/market_observers.py).

Snapshot returns current levels with day deltas for every symbol in
every watchlist. Failing symbols degrade silently (graceful
degradation): a dead ticker never breaks the rest.
"""

from __future__ import annotations

from dataclasses import dataclass

from runtime.observers.providers.yfinance_provider import ObserverError, fetch_quote

DEFAULT_WATCHLISTS: dict[str, list[str]] = {
    "default": [
        "^BVSP",
        "USDBRL=X",
        "^IRX",
        "^TNX",
        "^TYX",
        "^FVX",
        "^GSPC",
        "^IXIC",
        "^DJI",
        "^RUT",
        "^VIX",
        "GC=F",
        "CL=F",
        "SI=F",
        "HG=F",
        "DX-Y.NYB",
        "EURUSD=X",
        "JPY=X",
        "CNY=X",
    ],
    "brasil": ["^BVSP", "USDBRL=X", "^IRX", "^TNX"],
    "global_rates": ["^IRX", "^FVX", "^TNX", "^TYX", "DE10Y.F"],
    "commodities": ["GC=F", "CL=F", "SI=F", "HG=F", "PL=F", "BZ=F"],
}


@dataclass
class WatchlistItem:
    symbol: str
    level: float | None
    delta_pct_1d: float | None
    status: str  # "ok" / "no_data" / "error"


def list_watchlists() -> dict:
    return {"watchlists": list(DEFAULT_WATCHLISTS)}


def snapshot(watchlist: str) -> dict:
    symbols = DEFAULT_WATCHLISTS.get(watchlist)
    if symbols is None:
        return {"error": f"unknown watchlist: {watchlist}", "available": list_watchlists()["watchlists"]}
    items: list[WatchlistItem] = []
    for symbol in symbols:
        try:
            q = fetch_quote(symbol)
        except ObserverError:
            items.append(WatchlistItem(symbol=symbol, level=None, delta_pct_1d=None, status="no_data"))
            continue
        except Exception:
            items.append(WatchlistItem(symbol=symbol, level=None, delta_pct_1d=None, status="error"))
            continue
        price = q.get("price")
        prev = q.get("previous_close")
        delta = None
        if price is not None and prev:
            delta = round((price - prev) / prev * 100, 2)
        items.append(WatchlistItem(symbol=symbol, level=price, delta_pct_1d=delta, status="ok"))
    return {
        "watchlist": watchlist,
        "items": [
            {"symbol": i.symbol, "level": i.level, "delta_pct_1d": i.delta_pct_1d, "status": i.status} for i in items
        ],
    }
