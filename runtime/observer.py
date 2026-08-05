"""FlowCore — SCPX Observer Engine (Sprint 18, Fase 1).

The "Market Data" stage of the SCPX pipeline documented in
FLOWCORE_CONSTITUTION.md ("SCPX Vision"): fetches live macro/market
indicators via yfinance. Later phases (Macro Score Engine, Portfolio
Impact, Recommendation, Alert) consume this data — this module only
observes, it never scores or decides.

Scope confirmed with the user: only indicators with an already-working
data source. DI futuro (API MDS B3 is down, brapi.dev doesn't cover DI
futures) and Notícias (needs a new external provider decision) are
deferred, not included here.

Live snapshot only — no persistence/history. A history table becomes a
real requirement once Fase 2 (Macro Score Engine) actually needs windowed
data; building it now would have no consumer.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import yfinance as yf

SYMBOLS = {
    "treasury_10y": "^TNX",
    "usd_brl": "USDBRL=X",
    "vix": "^VIX",
    "brent": "BZ=F",  # same Brent proxy signal-engine already uses
    "gold": "GC=F",
}

_CACHE_TTL_SECONDS = 30
_cache: dict[str, tuple[float, dict]] = {}


class ObserverError(RuntimeError):
    """Raised when a market data fetch fails (network, parsing, etc.)."""


def _to_float(value: Any) -> float | None:
    """Normalize yfinance's fast_info values to plain float.

    yfinance gotcha (per the user's known-issues list): recent versions
    sometimes return a pandas Series instead of a scalar. Always normalize
    before comparing/formatting.
    """
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fast_info_get(fast_info: Any, *keys: str) -> Any:
    """Read a field from yfinance's FastInfo, trying each key alias.

    Key casing varies by yfinance version (e.g. "last_price" vs
    "lastPrice") — try each candidate rather than assuming one.
    """
    for key in keys:
        try:
            value = fast_info[key]
        except (KeyError, TypeError):
            value = getattr(fast_info, key, None)
        if value is not None:
            return value
    return None


def _quote(symbol: str) -> dict:
    cached = _cache.get(symbol)
    if cached is not None:
        cached_at, cached_value = cached
        if time.monotonic() - cached_at < _CACHE_TTL_SECONDS:
            return cached_value

    try:
        fast_info = yf.Ticker(symbol).fast_info
        price = _to_float(_fast_info_get(fast_info, "last_price", "lastPrice"))
        previous_close = _to_float(_fast_info_get(fast_info, "previous_close", "previousClose"))
    except Exception as e:
        raise ObserverError(f"Failed to fetch {symbol}: {e}") from e

    if price is None:
        raise ObserverError(f"No price data returned for {symbol}")

    change_pct = None
    if previous_close:
        change_pct = (price - previous_close) / previous_close * 100

    result = {
        "symbol": symbol,
        "price": price,
        "previous_close": previous_close,
        "change_pct": change_pct,
        "checked_at": datetime.now(UTC).isoformat(),
    }
    _cache[symbol] = (time.monotonic(), result)
    return result


def get_indicator(name: str) -> dict:
    if name not in SYMBOLS:
        raise ObserverError(f"Unknown indicator: {name!r}")
    result = _quote(SYMBOLS[name])
    return {"name": name, **result}


def check_health() -> dict:
    """Live reachability probe — a single lightweight fetch (VIX)."""
    return get_indicator("vix")
