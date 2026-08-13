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

import pandas as pd
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


def _history_once(symbol: str, days: int) -> list[float]:
    """Last `days` daily closes for `symbol` (ascending, oldest first).

    Uses yfinance download (more reliable for history than history()).
    Raises ObserverError when Yahoo returns nothing or malformed data.
    """
    end = time.time()
    start = end - days * 86400
    # yfinance's download() may reject raw float timestamps on some
    # versions — pass datetime objects instead.
    import datetime as _dt
    start_dt = _dt.datetime.fromtimestamp(start, tz=_dt.timezone.utc)
    end_dt = _dt.datetime.fromtimestamp(end, tz=_dt.timezone.utc)

    def _do_download(kwargs: dict) -> Any:
        return yf.download(symbol, auto_adjust=True, progress=False,
                           timeout=_DEFAULT_TIMEOUT_SECONDS, **kwargs)

    df: Any = None
    last_err: Exception | None = None
    # Yahoo intermittently answers "possibly delisted" for perfectly valid
    # tickers — retry up to 3 times, alternating parameter shapes, before
    # giving up (the caller reports an honest absence).
    for attempt in range(3):
        try:
            if attempt == 2:
                df = _do_download({"period": "3mo"})
            else:
                df = _do_download({"start": start_dt, "end": end_dt})
            if df is not None and not (hasattr(df, "empty") and df.empty):
                break
            last_err = ObserverError(f"No history data returned for {symbol}")
        except Exception as exc:  # noqa: BLE001
            last_err = ObserverError(f"History download failed for {symbol}: {exc}")
        time.sleep(0.5 * (attempt + 1))
    if df is None or (hasattr(df, "empty") and df.empty):
        assert last_err is not None
        raise last_err
    close_col = "Close"
    if hasattr(df, "columns"):
        cols = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        if "Adj Close" in cols:
            close_col = "Adj Close"
        elif "Close" not in cols:
            raise ObserverError(f"No Close column in history for {symbol}")
        # MultiIndex columns (e.g. ('Close', 'GC=F')): pick the tuple whose
        # first element matches, using the single-symbol level otherwise.
        if isinstance(df.columns, pd.MultiIndex):
            candidates = [c for c in df.columns
                          if isinstance(c, tuple) and c[0] == close_col]
            close_col = candidates[0] if candidates else df.columns[0]
    try:
        series = df[close_col]
        # yfinance may return a DataFrame (MultiIndex columns) instead of
        # a Series on some versions — take the first column in that case.
        if hasattr(series, "columns"):
            series = series[series.columns[0]]
        closes = [_to_float(v) for v in series.tolist()]
    except (KeyError, ValueError, TypeError, IndexError):
        raise ObserverError(f"Malformed history payload for {symbol}") from None
    closes = [c for c in closes if c is not None]
    if not closes:
        raise ObserverError(f"No valid closes in history for {symbol}")
    return closes


def fetch_history(
    symbol: str,
    days: int = 60,
    timeout: float = _DEFAULT_TIMEOUT_SECONDS * 3,
) -> list[float]:
    """Cached history fetch (10-min TTL — daily data changes rarely).

    Returns list of daily close prices, oldest first. Cached under a
    (symbol, days-bucket) key so the same window isn't re-downloaded on
    every call.
    """
    key = (symbol, days // 10 * 10)
    cached = _cache.get(key)
    if cached and (time.time() - cached[0]) < 600:
        return cached[1]
    try:
        closes = _executor.submit(_history_once, symbol, days).result(timeout=timeout)
    except (FutureTimeoutError, TimeoutError):
        raise ObserverError(f"History fetch timed out for {symbol}") from None
    _cache[key] = (time.time(), closes)
    return closes


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
