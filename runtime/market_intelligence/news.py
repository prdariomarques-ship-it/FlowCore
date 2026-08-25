"""News Intelligence — real headlines from yfinance, deterministic
categorization, zero fabrication.

Sources: yfinance's news feed per watched symbol (Yahoo Finance news,
public). Each item keeps only what the source provides: headline,
publisher, link, providerPublishTime. Nothing is invented, summarized
beyond the headline, or attributed beyond the source's own text.

Categorization is keyword-driven (macro / fed / geopolitics /
commodities / equities / fixed_income / technology / banking /
brazil / global) and conservative: if nothing matches, the category is
"global" — never a guessed label pretending to be specific.

Affected-asset inference: symbols whose news feed returned the item are
attached verbatim — no extrapolation to unrelated assets.
"""

from __future__ import annotations

import datetime as _dt
from concurrent.futures import ThreadPoolExecutor, as_completed

import yfinance as yf

_SYMBOL_GROUPS: dict[str, list[str]] = {
    "brazil": ["^BVSP", "USDBRL=X"],
    "us_equities": ["^GSPC", "^IXIC", "^DJI"],
    "rates": ["^TNX", "^FVX"],
    "commodities": ["BZ=F", "GC=F", "CL=F"],
    "fx": ["DX-Y.NYB", "EURUSD=X", "JPY=X"],
    "global": ["^N225", "^HSI", "^STOXX50E"],
}

_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("fed", ["fed", "fomc", "powell", "interest rate", "rate decision"]),
    ("copom", ["copom", "selic", "bc do brasil", "banco central"]),
    ("ecb", ["ecb", "lagarde", "european central bank"]),
    ("boj", ["boj", "bank of japan", "ueda"]),
    ("geopolitics", ["war", "conflict", "sanctions", "tariff", "trade war",
                     "geopolitical", "missile", "invasion"]),
    ("commodities", ["oil", "crude", "gold", "copper", "commodity", "brent", "wti"]),
    ("fixed_income", ["treasury", "yield", "bond", "debt", "default"]),
    ("inflation", ["cpi", "inflation", "ipca", "pce", "price index"]),
    ("employment", ["payroll", "jobs", "unemployment", "jobless"]),
    ("technology", ["ai", "nvidia", "chip", "semiconductor", "tech", "apple",
                    "openai", "datacenter"]),
    ("banking", ["bank", "credit", "lending", "basel"]),
    ("brazil", ["brazil", "brasil", "ibovespa", "real", "lula"]),
]


def _fetch_news(symbol: str) -> list[dict]:
    try:
        ticker = yf.Ticker(symbol)
        items = ticker.news or []
    except Exception:  # noqa: BLE001
        return []
    out: list[dict] = []
    for it in items:
        try:
            content = it.get("content") or {}
            title = content.get("title") or (it.get("title") or "").strip()
            if not title:
                continue
            pub = None
            if isinstance(it.get("provider"), dict):
                pub = it["provider"].get("displayName")
            elif isinstance(content.get("provider"), dict):
                pub = content["provider"].get("displayName")
            link = ""
            cu = content.get("canonicalUrl")
            if isinstance(cu, dict):
                link = cu.get("url", "") or cu.get("raw", "")
            link = link or content.get("previewUrl") or it.get("link") or ""
            ts = (content.get("pubDate") or it.get("providerPublishTime"))
            if isinstance(ts, (int, float)):
                ts = _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc).isoformat()
            out.append({
                "headline": title,
                "publisher": pub or (it.get("publisher") or ""),
                "link": link,
                "timestamp": ts or "",
                "related_symbol": symbol,
            })
        except Exception:  # noqa: BLE001
            continue
    return out


def fetch_news(symbols: list[str] | None = None, max_per_group: int = 6) -> dict:
    """Fetch news across symbol groups; dedupe by (headline, publisher)."""
    groups = symbols or list(_SYMBOL_GROUPS.keys())
    # Group names and explicit tickers can be mixed: expand each entry by the
    # matching rule — known group → its symbols; otherwise → literal ticker.
    todo: dict[str, list[str]] = {}
    for g in groups:
        if g in _SYMBOL_GROUPS:
            todo[g] = _SYMBOL_GROUPS[g]
        else:
            todo.setdefault("custom", []).append(g)
    if not todo:
        return {"items": [], "fetched_at": _dt.datetime.now(_dt.timezone.utc).isoformat()}

    items: list[dict] = []
    seen: set[tuple[str, str]] = set()
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(_fetch_news, s): s
                   for syms in todo.values() for s in syms}
        for fut in as_completed(futures):
            for it in fut.result():
                key = (it["headline"][:80].lower(), it["publisher"].lower())
                if key in seen:
                    continue
                seen.add(key)
                it["category"] = _categorize(it["headline"])
                it["related_region"] = _region_for(it["related_symbol"])
                items.append(it)

    items.sort(key=lambda x: x["timestamp"], reverse=True)
    per_group = max_per_group * len(groups)
    return {"items": items[:per_group or len(items)],
            "fetched_at": _dt.datetime.now(_dt.timezone.utc).isoformat()}


def _categorize(headline: str) -> str:
    lower = headline.lower()
    for cat, kws in _CATEGORY_KEYWORDS:
        if any(k in lower for k in kws):
            return cat
    return "global"


def _region_for(symbol: str) -> str:
    if symbol in ("^BVSP", "USDBRL=X"):
        return "brazil"
    if symbol in ("^N225", "^HSI", "000001.SS", "JPY=X", "CNY=X"):
        return "asia"
    if symbol in ("^STOXX50E", "^GDAXI", "^FTSE", "EURUSD=X"):
        return "europe"
    return "us"
