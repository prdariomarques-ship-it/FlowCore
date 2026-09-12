"""User-defined symbol watchlists — real data only via yfinance.

Watchlists are names mapping to lists of Yahoo Finance tickers. The
default watchlist covers the core market set already validated against
live yfinance (see runtime/observers/market_observers.py).

Snapshot returns current levels with day deltas for every symbol in
every watchlist. Failing symbols degrade silently (graceful
degradation): a dead ticker never breaks the rest.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import TYPE_CHECKING

from runtime.observers.providers.ptax_provider import fetch_usdbrl_ptax
from runtime.observers.providers.yfinance_provider import ObserverError, fetch_quote

DEFAULT_WATCHLISTS: dict[str, list[str]] = {
    "default": ["^BVSP", "USDBRL=X", "^IRX", "^TNX", "^TYX", "^FVX",
                "^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX", "GC=F", "CL=F",
                "SI=F", "HG=F", "DX-Y.NYB", "EURUSD=X", "JPY=X", "CNY=X",
                "^FTSE", "^GDAXI", "^FCHI", "^KS11"],
    "brasil": ["^BVSP", "USDBRL=X", "^IRX", "^TNX"],
    "global_rates": ["^IRX", "^FVX", "^TNX", "^TYX", "DE10Y.F"],
    "commodities": ["GC=F", "CL=F", "SI=F", "HG=F", "PL=F", "BZ=F"],
    # Compact operational feed for dashboard, Telegram and mobile clients.
    # Detailed watchlists remain available through the endpoint below.
    "mobile_core": ["^BVSP", "USDBRL=X", "^GSPC", "^TNX"],
}


@dataclass
class WatchlistItem:
    symbol: str
    level: float | None
    delta_pct_1d: float | None
    status: str  # "ok" / "no_data" / "error"
    # The real exception text from the failed fetch (or its fallback, if
    # one was tried) -- previously discarded entirely, so a whole tab
    # showing "fonte indisponível" gave no way to tell a timeout from an
    # auth error from Yahoo simply blocking this network's requests.
    error: str | None = None


def list_watchlists() -> dict:
    return {"watchlists": list(DEFAULT_WATCHLISTS)}


def _try_fallback(symbol: str) -> dict | None:
    """None if this symbol has no fallback, or the fallback itself fails
    too -- the caller then reports the original failure honestly rather
    than a fabricated value.

    Only USDBRL=X has one today, because it's the "Câmbio" group's single
    indicator (config/market_thresholds.py) -- a yfinance hiccup there
    empties the whole tab, unlike Índices/Commodities/Juros which have
    several indicators each. PTAX (Banco Central) is an independent
    source that never depends on Yahoo Finance's availability."""
    if symbol != "USDBRL=X":
        return None
    try:
        return fetch_usdbrl_ptax()
    except Exception:
        return None


def snapshot(watchlist: str) -> dict:
    symbols = DEFAULT_WATCHLISTS.get(watchlist)
    if symbols is None:
        return {"error": f"unknown watchlist: {watchlist}",
                "available": list_watchlists()["watchlists"]}
    fetched: dict[str, WatchlistItem] = {}

    def fetch_item(symbol: str) -> WatchlistItem:
        try:
            # This snapshot originally called fetch_quote with timeout=2.5,
            # retries=0. Real device logs (once the error field below
            # started being surfaced instead of discarded) showed
            # commodities still timing out at 6.0s/1 retry -- 16 workers
            # opening 16 simultaneous HTTPS connections likely oversubscribes
            # a constrained mobile connection, so every one of them
            # individually starves rather than a handful succeeding.
            # Falling back fully to fetch_quote()'s own tuned defaults
            # (timeout=10.0, retries=2) with less parallelism below.
            q = fetch_quote(symbol)
        except ObserverError as exc:
            q = _try_fallback(symbol)
            if q is None:
                return WatchlistItem(symbol=symbol, level=None, delta_pct_1d=None, status="no_data", error=str(exc))
        except Exception as exc:
            q = _try_fallback(symbol)
            if q is None:
                return WatchlistItem(symbol=symbol, level=None, delta_pct_1d=None, status="error", error=str(exc))
        price = q.get("price")
        prev = q.get("previous_close")
        delta = None
        if price is not None and prev:
            delta = round((price - prev) / prev * 100, 2)
        return WatchlistItem(symbol=symbol, level=price, delta_pct_1d=delta, status="ok")

    # fetch_quote() blocks synchronously per call, so this pool's worker
    # count -- not the shared internal one in yfinance_provider.py -- is
    # what actually bounds how many symbols fetch concurrently. 16
    # concurrent HTTPS connections against Yahoo from one constrained
    # mobile connection appears to starve all of them rather than let a
    # handful through fast; a moderate 6 keeps some parallelism without
    # trying to open that many sockets at once.
    with ThreadPoolExecutor(max_workers=min(6, len(symbols))) as executor:
        futures = {executor.submit(fetch_item, symbol): symbol for symbol in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                fetched[symbol] = future.result()
            except Exception as exc:
                fetched[symbol] = WatchlistItem(symbol=symbol, level=None, delta_pct_1d=None, status="error", error=str(exc))

    items = [fetched[symbol] for symbol in symbols]
    return {"watchlist": watchlist,
            "items": [{"symbol": i.symbol, "level": i.level,
                       "delta_pct_1d": i.delta_pct_1d,
                       "status": i.status, "error": i.error} for i in items]}
