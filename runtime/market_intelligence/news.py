"""News intelligence with traceable Yahoo Finance provenance.

The public feed is intentionally conservative: headlines, publishers, canonical
links, publication times and affected assets are preserved from the provider.
No article body, summary or market interpretation is fabricated.  The module
normalizes these fields into a stable contract shared by the dashboard, mobile
application and briefing generator.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import yfinance as yf

_YAHOO_FINANCE_URL = "https://finance.yahoo.com/"

_SYMBOL_GROUPS: dict[str, list[str]] = {
    "brazil": ["^BVSP", "USDBRL=X"],
    "us_equities": ["^GSPC", "^IXIC", "^DJI"],
    "rates": ["^TNX", "^FVX"],
    "commodities": ["BZ=F", "GC=F", "CL=F"],
    "fx": ["DX-Y.NYB", "EURUSD=X", "JPY=X"],
    "global": ["^N225", "^HSI", "^STOXX50E"],
}

_SECTION_GROUPS: dict[str, list[str]] = {
    "all": list(_SYMBOL_GROUPS),
    "brasil": ["brazil"],
    "eua": ["us_equities"],
    "mundo": ["global"],
    "juros": ["rates"],
    "empresas": ["brazil", "us_equities"],
    "commodities": ["commodities"],
    "ia": ["us_equities"],
}
SUPPORTED_NEWS_SECTIONS = tuple(_SECTION_GROUPS)

_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("fed", ["fed", "fomc", "powell", "interest rate", "rate decision"]),
    ("copom", ["copom", "selic", "bc do brasil", "banco central"]),
    ("ecb", ["ecb", "lagarde", "european central bank"]),
    ("boj", ["boj", "bank of japan", "ueda"]),
    ("geopolitics", ["war", "conflict", "sanctions", "tariff", "trade war", "geopolitical", "missile", "invasion"]),
    ("commodities", ["oil", "crude", "gold", "copper", "commodity", "brent", "wti"]),
    ("fixed_income", ["treasury", "yield", "bond", "debt", "default"]),
    ("inflation", ["cpi", "inflation", "ipca", "pce", "price index"]),
    ("employment", ["payroll", "jobs", "unemployment", "jobless"]),
    ("technology", ["ai", "nvidia", "chip", "semiconductor", "tech", "apple", "openai", "datacenter"]),
    ("banking", ["bank", "credit", "lending", "basel"]),
    ("brazil", ["brazil", "brasil", "ibovespa", "real", "lula"]),
]

_RATES_CATEGORIES = {"fed", "copom", "ecb", "boj", "fixed_income", "inflation"}
_COMPANY_CATEGORIES = {"technology", "banking"}


def _fetch_news(symbol: str) -> list[dict[str, Any]]:
    """Read only the fields supplied by yfinance for one watched symbol."""
    try:
        ticker = yf.Ticker(symbol)
        items = ticker.news or []
    except Exception:  # noqa: BLE001 - source failures become an empty source slice
        return []

    out: list[dict[str, Any]] = []
    for item in items:
        try:
            content = item.get("content") or {}
            headline = (content.get("title") or item.get("title") or "").strip()
            if not headline:
                continue
            publisher = ""
            if isinstance(item.get("provider"), dict):
                publisher = item["provider"].get("displayName") or ""
            elif isinstance(content.get("provider"), dict):
                publisher = content["provider"].get("displayName") or ""
            canonical = content.get("canonicalUrl")
            link = canonical.get("url", "") or canonical.get("raw", "") if isinstance(canonical, dict) else ""
            link = link or content.get("previewUrl") or item.get("link") or ""
            published_at = content.get("pubDate") or item.get("providerPublishTime") or ""
            if isinstance(published_at, (int, float)):
                published_at = _dt.datetime.fromtimestamp(published_at, tz=_dt.timezone.utc).isoformat()
            out.append({
                "headline": headline,
                "publisher": publisher or item.get("publisher") or "",
                "link": link,
                "timestamp": str(published_at) if published_at else "",
                "related_symbol": symbol,
            })
        except Exception:  # noqa: BLE001 - malformed provider items are ignored individually
            continue
    return out


def _categorize(headline: str) -> str:
    lower = headline.lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in lower for keyword in keywords):
            return category
    return "global"


def _region_for(symbol: str) -> str:
    if symbol in ("^BVSP", "USDBRL=X"):
        return "brazil"
    if symbol in ("^N225", "^HSI", "000001.SS", "JPY=X", "CNY=X"):
        return "asia"
    if symbol in ("^STOXX50E", "^GDAXI", "^FTSE", "EURUSD=X"):
        return "europe"
    return "us"


def _expand_groups(groups: list[str]) -> dict[str, list[str]]:
    expanded: dict[str, list[str]] = {}
    for group in groups:
        if group in _SYMBOL_GROUPS:
            expanded[group] = _SYMBOL_GROUPS[group]
        else:
            expanded.setdefault("custom", []).append(group)
    return expanded


def _matches_section(item: dict[str, Any], section: str) -> bool:
    if section == "all":
        return True
    category = item["category"]
    region = item["related_region"]
    if section == "brasil":
        return region == "brazil" or category == "brazil"
    if section == "eua":
        return region == "us"
    if section == "mundo":
        return region in {"asia", "europe"} or category == "global"
    if section == "juros":
        return category in _RATES_CATEGORIES or item["related_symbol"] in _SYMBOL_GROUPS["rates"]
    if section == "empresas":
        return category in _COMPANY_CATEGORIES
    if section == "commodities":
        return category == "commodities" or item["related_symbol"] in _SYMBOL_GROUPS["commodities"]
    if section == "ia":
        return category == "technology"
    return False


def _sections_for(item: dict[str, Any]) -> list[str]:
    return [section for section in SUPPORTED_NEWS_SECTIONS if section != "all" and _matches_section(item, section)]


def _decode_cursor(cursor: str | None) -> int:
    if cursor in (None, ""):
        return 0
    if not cursor.isdecimal():
        raise ValueError("cursor must be a non-negative integer")
    return int(cursor)


def _normalize_item(item: dict[str, Any], collected_at: str) -> dict[str, Any]:
    published_at = item["timestamp"] or None
    canonical_url = item["link"] or None
    stable_key = "|".join((canonical_url or "", item["publisher"], item["headline"], published_at or ""))
    return {
        # Stable fields for the mobile and web feed.
        "id": hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:24],
        "headline": item["headline"],
        "section_tags": _sections_for(item),
        "category": item["category"],
        "related_region": item["related_region"],
        "publisher": item["publisher"] or None,
        "provider": {"id": "yahoo_finance", "name": "Yahoo Finance", "url": _YAHOO_FINANCE_URL},
        "canonical_url": canonical_url,
        "published_at": published_at,
        "collected_at": collected_at,
        "related_assets": [item["related_symbol"]],
        "status": "ok",
        # Legacy aliases retained for existing consumers.
        "link": item["link"],
        "timestamp": item["timestamp"],
        "related_symbol": item["related_symbol"],
    }


def fetch_news(
    symbols: list[str] | None = None,
    max_per_group: int = 6,
    *,
    section: str = "all",
    cursor: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Return a source-attributed, optionally paginated news feed.

    `symbols` and `max_per_group` are retained for the briefing generator.
    Mobile/web callers should use `section`, `cursor` and `limit`.
    """
    if section not in SUPPORTED_NEWS_SECTIONS:
        raise ValueError(f"unsupported news section: {section}")
    offset = _decode_cursor(cursor)
    groups = symbols or _SECTION_GROUPS[section]
    expanded = _expand_groups(groups)
    if not expanded:
        collected_at = _dt.datetime.now(_dt.timezone.utc).isoformat()
        return {
            "items": [], "groups": [], "section": section, "supported_sections": list(SUPPORTED_NEWS_SECTIONS),
            "next_cursor": None, "fetched_at": collected_at, "partial_errors": [], "source": "yahoo_finance",
        }

    raw_items: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    with ThreadPoolExecutor(max_workers=min(6, sum(len(symbols) for symbols in expanded.values())), thread_name_prefix="flowcore-news") as executor:
        futures = {executor.submit(_fetch_news, symbol): symbol for symbols in expanded.values() for symbol in symbols}
        for future in as_completed(futures):
            for item in future.result():
                key = (item["headline"][:160].lower(), item["publisher"].lower(), item["link"])
                if key in seen:
                    continue
                seen.add(key)
                item["category"] = _categorize(item["headline"])
                item["related_region"] = _region_for(item["related_symbol"])
                raw_items.append(item)

    raw_items.sort(key=lambda item: item["timestamp"], reverse=True)
    filtered_items = [item for item in raw_items if _matches_section(item, section)]
    collected_at = _dt.datetime.now(_dt.timezone.utc).isoformat()
    normalized = [_normalize_item(item, collected_at) for item in filtered_items]
    page_size = max(1, limit if limit is not None else max_per_group * len(groups))
    page = normalized[offset:offset + page_size]
    next_offset = offset + len(page)
    return {
        "items": page,
        "groups": list(expanded),
        "section": section,
        "supported_sections": list(SUPPORTED_NEWS_SECTIONS),
        "next_cursor": str(next_offset) if next_offset < len(normalized) else None,
        "fetched_at": collected_at,
        "partial_errors": [],
        "source": "yahoo_finance",
    }
