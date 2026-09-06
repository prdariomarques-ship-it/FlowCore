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
"""
from __future__ import annotations

MARKET_THRESHOLDS: dict[str, dict] = {
    "ibovespa": {"symbol": "^BVSP", "label": "Ibovespa", "unit": "percent", "high": 1.5, "medium": 0.7},
    "sp500": {"symbol": "^GSPC", "label": "S&P 500", "unit": "percent", "high": 1.2, "medium": 0.5},
    "nasdaq": {"symbol": "^IXIC", "label": "Nasdaq", "unit": "percent", "high": 1.5, "medium": 0.7},
    "usdbrl": {"symbol": "USDBRL=X", "label": "Dólar", "unit": "percent", "high": 1.0, "medium": 0.4},
    "us10y": {"symbol": "^TNX", "label": "US Treasury 10Y", "unit": "percentage_points", "high": 0.10, "medium": 0.05},
    # No B3 futures feed is connected — DI Jan has no real source today.
    # Kept in the catalog (symbol=None) so MarketAgent reports it as an
    # explicit MOCK entry instead of silently omitting an indicator the
    # spec asked for.
    "di": {"symbol": None, "label": "DI Jan (futuro)", "unit": "percentage_points", "high": 0.10, "medium": 0.05},
    "gold": {"symbol": "GC=F", "label": "Ouro", "unit": "percent", "high": 1.5, "medium": 0.7},
    "oil": {"symbol": "CL=F", "label": "Petróleo (WTI)", "unit": "percent", "high": 3.0, "medium": 1.5},
    "copper": {"symbol": "HG=F", "label": "Cobre", "unit": "percent", "high": 2.0, "medium": 1.0},
}
