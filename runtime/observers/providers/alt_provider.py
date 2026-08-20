"""Alternative market data providers for FlowCore Observers.

Provides non-yfinance sources used as backup/enrichment channels so the
dashboard never goes blank when Yahoo Finance is slow or down (a known
production issue on the user's host). Composition over modification:
observers keep calling fetch_quote() through their own provider; this
module only adds two new fetchers, each with its own cache.

Sources (tested 2026-08-20):
- TradingEconomics: meta-description parsing of country pages
  (brazil/government-bond-yield, brazil/currency, brazil/stock-market,
  germany/stock-market, united-kingdom/stock-market, euro-area/stock-market)
- Frankfurter: https://api.frankfurter.app (free, no key) for FX rates
  (USD->BRL/EUR, and BRL->cross rates)

Both are intentionally separate from yfinance_provider.py so a failure in
one never contaminates the other's cache or thread pool.
"""
from __future__ import annotations

import html
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from runtime.observers.base import ObserverError

_ALT_CACHE_TTL_SECONDS = 300  # 5 min: these sources update daily/intraday
_alt_cache: dict[str, tuple[float, dict]] = {}
_SESSION_TIMEOUT_SECONDS = 20
_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="observer-alt")


def _session() -> requests.Session:
    session = requests.Session()
    retries = Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return session


def _cached(key: str, fetcher):
    """Return a cached dict when fresh; otherwise run fetcher() and cache it.

    A fetcher may raise ObserverError; callers get a single uniform exception.
    """
    now = time.time()
    entry = _alt_cache.get(key)
    if entry is not None and now - entry[0] < _ALT_CACHE_TTL_SECONDS:
        return entry[1]
    result = fetcher()
    _alt_cache[key] = (now, result)
    return result


def _te_extract(text: str) -> dict | None:
    """Pull headline value + context from a TradingEconomics meta description.

    Example: 'The yield on Brazil 10Y Bond Yield eased to 14.82% on August 19,
    2026, marking a 0.05 percentage points decrease from the previous session.'
    Returns {"value": float, "delta_pct": float or None, "date": str or None}
    or None when no numeric headline is found.
    """
    m = re.search(r'content="([^"]*(?:to|of|at|rose|fell|eased|gained|lost|climbed|declined)[^"]*)"', text, re.S)
    if not m:
        return None
    desc = html.unescape(m.group(1))

    # headline value: number possibly followed by %/points/points a
    vm = re.search(r"(to|of|at)\s*(-?\d{1,6}(?:[.,]\d+)?\d{0,3})\s*(%|\s*points|percent)?", desc, re.I)
    value = None
    if vm:
        raw = vm.group(2).replace(",", ".")
        try:
            value = float(raw)
        except ValueError:
            return None

    # session delta: 'gaining 0.90%', 'losing 0.63%', 'up 0.36%', 'down 1.2%'
    dm = re.search(
        r"(gaining|losing|up|down|gain|loss|increase|decrease)[^\d]{0,60}(-?\d{1,6}(?:[.,]\d+)?)\s*%",
        desc,
        re.I,
    )
    delta_pct = None
    if dm:
        direction = dm.group(1).lower()
        try:
            raw = dm.group(2).replace(",", ".")
            delta_pct = float(raw)
            if direction in ("losing", "down", "loss", "decrease"):
                delta_pct = -abs(delta_pct)
            elif direction in ("gaining", "up", "gain", "increase"):
                delta_pct = +abs(delta_pct)
        except ValueError:
            delta_pct = None

    # headline date
    date_m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+2\d{3}", desc)
    date = date_m.group(0) if date_m else None

    return {"value": value, "delta_pct": delta_pct, "date": date}


def _fetch_te_page(page: str) -> dict:
    """Fetch one TradingEconomics page and parse its meta description."""
    session = _session()
    try:
        future = _executor.submit(session.get, f"https://tradingeconomics.com/{page}", timeout=_SESSION_TIMEOUT_SECONDS)
        response = future.result(timeout=_SESSION_TIMEOUT_SECONDS)
    except FutureTimeoutError as exc:
        raise ObserverError(f"TradingEconomics timeout for {page}") from exc
    except requests.RequestException as exc:
        raise ObserverError(f"TradingEconomics network error for {page}: {exc}") from exc
    if response.status_code != 200:
        raise ObserverError(f"TradingEconomics HTTP {response.status_code} for {page}")
    extracted = _te_extract(response.text)
    if extracted is None or extracted.get("value") is None:
        raise ObserverError(f"TradingEconomics returned no headline value for {page}")
    return extracted


def fetch_tradingeconomics(page: str) -> dict:
    """Fetch and cache a TE indicator page. Returns {"value", "delta_pct", "date"}."""
    key = f"te:{page}"
    try:
        return _cached(key, lambda: _fetch_te_page(page))
    except ObserverError as exc:
        _alt_cache.pop(key, None)  # don't cache failures
        raise exc


def _fetch_frankfurter(to: str, frm: str = "USD") -> dict:
    """Fetch latest FX rates from the Frankfurter API (no key needed)."""
    session = _session()
    try:
        future = _executor.submit(
            session.get,
            f"https://api.frankfurter.app/latest?from={frm}&to={to}",
            timeout=_SESSION_TIMEOUT_SECONDS,
        )
        response = future.result(timeout=_SESSION_TIMEOUT_SECONDS)
    except FutureTimeoutError as exc:
        raise ObserverError(f"Frankfurter timeout for {frm}->{to}") from exc
    except requests.RequestException as exc:
        raise ObserverError(f"Frankfurter network error: {exc}") from exc
    if response.status_code != 200:
        raise ObserverError(f"Frankfurter HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ObserverError("Frankfurter returned non-JSON") from exc
    rates = payload.get("rates") or {}
    if not rates:
        raise ObserverError(f"Frankfurter returned no rates for {frm}->{to}")
    return {"base": frm, "date": payload.get("date"), "rates": rates}


def fetch_frankfurter(to: str, frm: str = "USD") -> dict:
    """Fetch and cache Frankfurter FX rates."""
    key = f"fr:{frm}:{to}"
    try:
        return _cached(key, lambda: _fetch_frankfurter(to, frm))
    except ObserverError as exc:
        _alt_cache.pop(key, None)
        raise exc
