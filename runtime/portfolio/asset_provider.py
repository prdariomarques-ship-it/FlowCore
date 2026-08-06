"""Asset classification enrichment via yfinance.

Separate from runtime/observers/providers/yfinance_provider.py's
fast_info-based fetch_quote — classification data (name, sector,
industry, country, currency, asset class) requires yfinance's heavier
Ticker.info call, a genuinely different API surface with its own shape
and failure modes.
"""

from __future__ import annotations

import yfinance as yf

_QUOTE_TYPE_TO_ASSET_CLASS = {
    "EQUITY": "equity",
    "ETF": "etf",
    "MUTUALFUND": "mutual_fund",
    "CRYPTOCURRENCY": "crypto",
    "INDEX": "index",
    "CURRENCY": "currency",
    "FUTURE": "future",
    "BOND": "bond",
}


class AssetProviderError(RuntimeError):
    """Raised when a symbol's classification can't be fetched (unknown ticker, network failure)."""


def fetch_asset_info(symbol: str) -> dict:
    """Fetch name/asset_class/country/currency/sector/industry for `symbol`.

    Raises AssetProviderError if the symbol doesn't exist (yfinance
    returns a near-empty info dict for unknown tickers rather than
    raising) or if the network call itself fails.
    """
    try:
        info = yf.Ticker(symbol).info
    except Exception as e:
        raise AssetProviderError(f"Failed to fetch info for {symbol}: {e}") from e

    name = info.get("longName") or info.get("shortName")
    if not name:
        raise AssetProviderError(f"Unknown symbol: {symbol!r}")

    quote_type = info.get("quoteType") or ""
    asset_class = _QUOTE_TYPE_TO_ASSET_CLASS.get(quote_type, quote_type.lower() or None)

    return {
        "name": name,
        "asset_class": asset_class,
        "country": info.get("country"),
        "currency": info.get("currency"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
    }
