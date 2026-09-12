"""Market-source catalog with source lineage and failure-safe public feeds.

This module does not synthesize quotes. Each observation carries its
provider, observation date and retrieval timestamp so dashboard, Telegram and
the APK can display provenance instead of mixing provider bases silently.
"""
from __future__ import annotations

import csv
import io
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

import httpx


BCB_SELIC_SERIES = 1178
BCB_BASE_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs"
TREASURY_CURVE_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve&"
    "field_tdr_date_value={year}&page&_format=csv"
)

SOURCE_CATALOG = [
    {
        "id": "bcb_sgs",
        "name": "Banco Central do Brasil — BCData/SGS",
        "tier": "official",
        "coverage": ["Selic e séries macroeconômicas brasileiras"],
        "authentication": "none",
        "url": "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados?formato=json",
    },
    {
        "id": "us_treasury",
        "name": "U.S. Department of the Treasury — Daily PAR Yield Curve",
        "tier": "official",
        "coverage": ["Treasuries 2Y, 5Y, 10Y e 30Y"],
        "authentication": "none",
        "url": "https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics",
    },
    {
        "id": "yahoo_finance",
        "name": "Yahoo Finance",
        "tier": "fallback",
        "coverage": ["índices, câmbio, commodities e bolsas globais"],
        "authentication": "none",
        "url": "https://finance.yahoo.com/",
    },
    {
        "id": "trading_economics",
        "name": "TradingEconomics",
        "tier": "optional_authenticated",
        "coverage": ["mercados, calendário econômico e séries históricas"],
        "authentication": "FLOWCORE_TRADING_ECONOMICS_KEY",
        "url": "https://docs.tradingeconomics.com/",
    },
    {
        "id": "wsj",
        "name": "The Wall Street Journal",
        "tier": "reference_only",
        "coverage": ["contexto e verificação editorial de mercado"],
        "authentication": "not_automated",
        "url": "https://www.wsj.com/market-data",
    },
]

_SOURCE_CACHE_TTL_SECONDS = 60
_source_cache: tuple[float, dict[str, Any]] | None = None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _unavailable(source: str, error: Exception) -> dict[str, Any]:
    return {"source": source, "available": False, "retrieved_at": _now(), "error": type(error).__name__}


def bcb_selic() -> dict[str, Any]:
    """Read the latest officially published Selic target series from BCB."""
    url = f"{BCB_BASE_URL}.{BCB_SELIC_SERIES}/dados/ultimos/2?formato=json"
    try:
        response = httpx.get(url, timeout=6)
        response.raise_for_status()
        rows = response.json()
        if not rows:
            raise ValueError("empty_series")
        latest = rows[-1]
        previous = rows[-2] if len(rows) > 1 else None
        value = float(str(latest["valor"]).replace(",", "."))
        previous_value = float(str(previous["valor"]).replace(",", ".")) if previous else None
        return {
            "source": "bcb_sgs",
            "available": True,
            "instrument": "SELIC_TARGET",
            "label": "Selic",
            "unit": "percent_per_year",
            "value": value,
            "previous_value": previous_value,
            "observation_date": latest["data"],
            "retrieved_at": _now(),
            "source_url": url,
        }
    except Exception as error:  # public-source failure must not break the market feed
        return _unavailable("bcb_sgs", error)


def us_treasury_curve() -> dict[str, Any]:
    """Read official daily PAR yields directly from U.S. Treasury CSV."""
    year = datetime.now(UTC).year
    url = TREASURY_CURVE_URL.format(year=year)
    try:
        response = httpx.get(url, timeout=4)
        response.raise_for_status()
        rows = list(csv.DictReader(io.StringIO(response.text)))
        if not rows:
            raise ValueError("empty_curve")
        latest = rows[0]
        previous = rows[1] if len(rows) > 1 else {}
        tenors = {"2Y": "2 Yr", "5Y": "5 Yr", "10Y": "10 Yr", "30Y": "30 Yr"}
        points = []
        for label, column in tenors.items():
            raw = latest.get(column)
            if raw in (None, "", "N/A"):
                continue
            prior_raw = previous.get(column)
            points.append({
                "source": "us_treasury",
                "instrument": f"US_TREASURY_{label}",
                "label": label,
                "unit": "percent_per_year",
                "value": float(raw),
                "previous_value": float(prior_raw) if prior_raw not in (None, "", "N/A") else None,
                "observation_date": latest.get("Date"),
            })
        return {"source": "us_treasury", "available": True, "points": points, "retrieved_at": _now(), "source_url": url}
    except Exception as error:  # public-source failure must not break the market feed
        return _unavailable("us_treasury", error)


def source_snapshot() -> dict[str, Any]:
    """Return the catalog and live official observations with explicit lineage."""
    global _source_cache
    if _source_cache and time.monotonic() - _source_cache[0] < _SOURCE_CACHE_TTL_SECONDS:
        return _source_cache[1]
    trading_economics_configured = bool(__import__("os").environ.get("FLOWCORE_TRADING_ECONOMICS_KEY"))
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="official-market-source") as executor:
        bcb_future = executor.submit(bcb_selic)
        treasury_future = executor.submit(us_treasury_curve)
        observations = [bcb_future.result(), treasury_future.result()]
    snapshot = {
        "catalog": SOURCE_CATALOG,
        "official_observations": observations,
        "optional_sources": [{"source": "trading_economics", "configured": trading_economics_configured}],
        "retrieved_at": _now(),
    }
    _source_cache = (time.monotonic(), snapshot)
    return snapshot
