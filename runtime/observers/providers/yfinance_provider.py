"""yfinance-backed quote fetching for market Observers.

Observers never touch yfinance directly (composition, not inheritance) —
they call fetch_quote() and build their own MarketEvent from the result.
This module owns everything provider-specific: normalization, retries,
timeouts, and a short-lived cache to avoid hammering Yahoo Finance.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any

import yfinance as yf

from runtime.observers.base import ObserverError

_CACHE_TTL_SECONDS = 30
_cache: dict[str, tuple[float, dict]] = {}

_DEFAULT_TIMEOUT_SECONDS = 10.0
_DEFAULT_RETRIES = 2
_RETRY_BACKOFF_SECONDS = 0.5

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="observer-yfinance")


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


def _fetch_once(symbol: str) -> dict:
    fast_info = yf.Ticker(symbol).fast_info
    price = _to_float(_fast_info_get(fast_info, "last_price", "lastPrice"))
    previous_close = _to_float(_fast_info_get(fast_info, "previous_close", "previousClose"))
    if price is None:
        raise ObserverError(f"No price data returned for {symbol}")
    return {"symbol": symbol, "price": price, "previous_close": previous_close}


def fetch_quote(
    symbol: str,
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    retries: int = _DEFAULT_RETRIES,
) -> dict:
    """Fetch a live quote for `symbol`, with a short cache, retries, and a timeout.

    Returns {"symbol", "price", "previous_close"}. Raises ObserverError on
    any unrecoverable failure (network, timeout, malformed/empty payload).
    """
    cached = _cache.get(symbol)
    if cached is not None:
        cached_at, cached_value = cached
        if time.monotonic() - cached_at < _CACHE_TTL_SECONDS:
            return cached_value

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        future = _executor.submit(_fetch_once, symbol)
        try:
            result = future.result(timeout=timeout)
        except FutureTimeoutError as e:
            future.cancel()
            last_error = ObserverError(f"Timed out fetching {symbol} after {timeout}s")
            last_error.__cause__ = e
        except ObserverError as e:
            last_error = e
        except Exception as e:
            last_error = ObserverError(f"Failed to fetch {symbol}: {e}")
            last_error.__cause__ = e
        else:
            _cache[symbol] = (time.monotonic(), result)
            return result

        if attempt < retries:
            time.sleep(_RETRY_BACKOFF_SECONDS)

    assert last_error is not None
    raise last_error
