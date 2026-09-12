"""Market movement relevance thresholds — MarketAgent (Wealth Copilot MVP 2).

Single place for "how big a move counts as HIGH/MEDIUM/LOW relevance" per
indicator, so this never gets hardcoded inside agents/market_agent.py or
scattered across call sites. Each entry:

  symbol: the yfinance ticker used by
          runtime.market_intelligence.watchlist.snapshot() — None means no
          real source is connected yet (MarketAgent reports it as MOCK,
          never silently blended with live data).
  label:  display name.
  unit:   "percent" (day change in %) for equities/FX/commodities, or
          "percentage_points" for yields, where a "move" is the absolute
          change in yield level (e.g. 4.10 -> 4.22 is +0.12 points), not a
          percent-of-percent calculation — that is how bond desks actually
          talk about rate moves, and it's what runtime/market_intelligence/
          yield_curve.py already uses for ^TNX (see its `delta` calc).
  high/medium: absolute thresholds (in `unit`) for HIGH vs MEDIUM
          relevance. Below `medium` is LOW. Deliberately explicit,
          auditable numbers — no statistical model, per the MVP2 spec's
          "regras explícitas e auditáveis" requirement.
  group:  which tab of the dashboard's "Inteligência de Mercado" card
          this indicator belongs to (indices/cambio/commodities/juros) —
          purely a display grouping, does not affect classification.
"""

from __future__ import annotations

MARKET_THRESHOLDS: dict[str, dict] = {
    "ibovespa": {
        "symbol": "^BVSP",
        "label": "Ibovespa",
        "unit": "percent",
        "high": 1.5,
        "medium": 0.7,
        "group": "indices",
    },
    "sp500": {"symbol": "^GSPC", "label": "S&P 500", "unit": "percent", "high": 1.2, "medium": 0.5, "group": "indices"},
    "nasdaq": {"symbol": "^IXIC", "label": "Nasdaq", "unit": "percent", "high": 1.5, "medium": 0.7, "group": "indices"},
    "dowjones": {
        "symbol": "^DJI",
        "label": "Dow Jones",
        "unit": "percent",
        "high": 1.2,
        "medium": 0.5,
        "group": "indices",
    },
    "ftse100": {
        "symbol": "^FTSE",
        "label": "FTSE 100",
        "unit": "percent",
        "high": 1.2,
        "medium": 0.5,
        "group": "indices",
    },
    "dax": {"symbol": "^GDAXI", "label": "DAX", "unit": "percent", "high": 1.5, "medium": 0.7, "group": "indices"},
    "cac40": {"symbol": "^FCHI", "label": "CAC 40", "unit": "percent", "high": 1.5, "medium": 0.7, "group": "indices"},
    "kospi": {"symbol": "^KS11", "label": "KOSPI", "unit": "percent", "high": 1.5, "medium": 0.7, "group": "indices"},
    "usdbrl": {
        "symbol": "USDBRL=X",
        "label": "Dólar",
        "unit": "percent",
        "high": 1.0,
        "medium": 0.4,
        "group": "cambio",
    },
    "eurusd": {"symbol": "EURUSD=X", "label": "Euro", "unit": "percent", "high": 0.8, "medium": 0.3, "group": "cambio"},
    "usdjpy": {"symbol": "JPY=X", "label": "Iene", "unit": "percent", "high": 0.8, "medium": 0.3, "group": "cambio"},
    "usdcny": {
        "symbol": "CNY=X",
        "label": "Renminbi",
        "unit": "percent",
        "high": 0.5,
        "medium": 0.2,
        "group": "cambio",
    },
    "us3m": {
        "symbol": "^IRX",
        "label": "US Treasury 3M",
        "unit": "percentage_points",
        "high": 0.08,
        "medium": 0.04,
        "group": "juros",
    },
    "us5y": {
        "symbol": "^FVX",
        "label": "US Treasury 5Y",
        "unit": "percentage_points",
        "high": 0.10,
        "medium": 0.05,
        "group": "juros",
    },
    "us10y": {
        "symbol": "^TNX",
        "label": "US Treasury 10Y",
        "unit": "percentage_points",
        "high": 0.10,
        "medium": 0.05,
        "group": "juros",
    },
    "us30y": {
        "symbol": "^TYX",
        "label": "US Treasury 30Y",
        "unit": "percentage_points",
        "high": 0.10,
        "medium": 0.05,
        "group": "juros",
    },
    # No B3 futures feed is connected — DI Jan has no real source today,
    # and the same is true for the médio/longo (DI Jan+1, DI Jan+2, ...)
    # points of the curve: there is no free, reliable API for B3's DI
    # futures curve in this codebase. Kept in the catalog (symbol=None)
    # so MarketAgent reports it as an explicit MOCK entry instead of
    # silently omitting an indicator the spec asked for -- adding fake
    # médio/longo entries here would violate that same rule, not fix it.
    "di": {
        "symbol": None,
        "label": "DI Jan (futuro)",
        "unit": "percentage_points",
        "high": 0.10,
        "medium": 0.05,
        "group": "juros",
    },
    "gold": {"symbol": "GC=F", "label": "Ouro", "unit": "percent", "high": 1.5, "medium": 0.7, "group": "commodities"},
    "oil": {
        "symbol": "CL=F",
        "label": "Petróleo (WTI)",
        "unit": "percent",
        "high": 3.0,
        "medium": 1.5,
        "group": "commodities",
    },
    "copper": {
        "symbol": "HG=F",
        "label": "Cobre",
        "unit": "percent",
        "high": 2.0,
        "medium": 1.0,
        "group": "commodities",
    },
    "silver": {
        "symbol": "SI=F",
        "label": "Prata",
        "unit": "percent",
        "high": 2.0,
        "medium": 1.0,
        "group": "commodities",
    },
    # Minério de ferro (iron ore, mainly traded on the Dalian Commodity
    # Exchange in China) has no reliable free ticker on Yahoo Finance --
    # SGX's TIO=F has repeatedly been delisted/unavailable there, and
    # Dalian's own contracts (i.e2405 etc.) aren't listed on Yahoo at
    # all. Not added rather than wired to a ticker likely to silently
    # break again; a real source (e.g. a paid data vendor) would be
    # needed for this one.
}

MARKET_GROUPS: dict[str, str] = {
    "indices": "Índices",
    "cambio": "Câmbio",
    "commodities": "Commodities",
    "juros": "Juros",
}
