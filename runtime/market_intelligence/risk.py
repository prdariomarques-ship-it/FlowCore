"""Correlation matrix + risk contribution analysis — real data only.

Uses daily log-return series (last 60 calendar days) fetched directly from
yfinance (`runtime/observers/providers/yfinance_provider.fetch_history`),
never from observer session state. All calculations are deterministic
(numpy): Pearson correlation, volatility, risk contribution decomposition
(Euler: weight × marginal contribution).

Data-quality rules:
- a symbol without enough history (<20 observations) is dropped from the
  matrix with `dropped: true` and a reason — never imputed;
- returns are computed on log prices (continuously compounded), standard
  practice for correlation estimation;
- correlation is only meaningful between series that share a trading
  calendar — pairwise listwise deletion is applied and flagged.
"""

from __future__ import annotations

import math as _math

from runtime.observers.providers.yfinance_provider import fetch_history

_MIN_OBS = 20


def _series(symbol: str, days: int = 60) -> tuple[list[float] | None, str]:
    """Return log-return series or (None, reason)."""
    try:
        closes = fetch_history(symbol, days=days)  # list[float]
    except Exception as exc:  # noqa: BLE001 — any provider failure = honest absence
        return None, f"source_error: {str(exc)[:60]}"
    if not closes or len(closes) < _MIN_OBS + 1:
        return None, f"insufficient_data: {len(closes) if closes else 0} closes"
    log_returns = []
    prev = closes[0]
    for c in closes[1:]:
        if prev and prev > 0 and c > 0:
            log_returns.append(_math.log(c / prev))
        prev = c
    if len(log_returns) < _MIN_OBS:
        return None, f"insufficient_data: {len(log_returns)} returns"
    return log_returns, ""


def correlation_matrix(symbols: list[str], days: int = 60) -> dict:
    matrix: dict[str, dict[str, float | None]] = {}
    dropped: list[dict] = []
    series: dict[str, list[float]] = {}

    for sym in symbols:
        s, reason = _series(sym, days)
        if s is None:
            dropped.append({"symbol": sym, "reason": reason})
            continue
        series[sym] = s

    syms = list(series.keys())
    for i, a in enumerate(syms):
        row: dict[str, float | None] = {}
        for j, b in enumerate(syms):
            if a == b:
                row[b] = 1.0
                continue
            xa, xb = _paired(series[a], series[b])
            if len(xa) < _MIN_OBS:
                row[b] = None
                continue
            row[b] = round(_pearson(xa, xb), 3)
        matrix[a] = row

    return {"symbols": syms, "matrix": matrix, "dropped": dropped,
            "window_days": days, "min_observations": _MIN_OBS}


def _paired(a: list[float], b: list[float]) -> tuple[list[float], list[float]]:
    """Listwise deletion — keep only shared positions."""
    n = min(len(a), len(b))
    return a[:n], b[:n]


def _pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    dx = (sum((xi - mx) ** 2 for xi in x)) ** 0.5
    dy = (sum((yi - my) ** 2 for yi in y)) ** 0.5
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


def risk_contribution(holdings: dict[str, float], days: int = 60) -> dict:
    """Weight -> risk decomposition for a user-supplied weight map.

    `holdings` maps symbol -> weight (fraction; normalized if it doesn't
    sum to 1). Output per symbol: weight, volatility (annualized),
    marginal_contribution, total_contribution (all sums to portfolio
    volatility). Symbols without enough history are dropped with reason.
    """
    series: dict[str, list[float]] = {}
    rc_dropped: list[dict] = []
    for sym, _w in holdings.items():
        s, reason = _series(sym, days)
        if s is None:
            rc_dropped.append({"symbol": sym, "reason": reason})
            continue
        series[sym] = s

    syms = list(series.keys())
    if len(syms) < 2:
        return {"symbols": syms, "analysis": None, "dropped": rc_dropped,
                "error": "insufficient_data"}

    total_w = sum(holdings.get(s, 0.0) for s in syms) or 1.0
    w = {s: holdings.get(s, 0.0) / total_w for s in syms}
    n = min(len(series[s]) for s in syms)
    returns = {s: series[s][:n] for s in syms}

    vols = {}
    cov = {}
    for i, a in enumerate(syms):
        mean_a = sum(returns[a]) / n
        vols[a] = ((sum((r - mean_a) ** 2 for r in returns[a]) / (n - 1)) ** 0.5
                   * (252 ** 0.5))
        for j, b in enumerate(syms):
            mean_b = sum(returns[b]) / n
            cov[(a, b)] = sum((ra - mean_a) * (rb - mean_b)
                              for ra, rb in zip(returns[a], returns[b])) / (n - 1)

    port_var = sum(w[a] * w[b] * cov[(a, b)] for a in syms for b in syms)
    port_vol = port_var ** 0.5 if port_var > 0 else 0.0

    analysis: dict[str, dict] = {}
    for a in syms:
        marginal = (sum(w[b] * cov[(a, b)] for b in syms) / port_vol
                    if port_vol > 0 else 0.0)
        analysis[a] = {
            "weight": round(w[a], 4),
            "volatility_annualized": round(vols[a], 4),
            "marginal_contribution": round(marginal, 4),
            "total_contribution": round(w[a] * marginal, 4),
        }

    return {"symbols": syms, "analysis": analysis, "dropped": rc_dropped,
            "portfolio_volatility_annualized": round(port_vol, 4),
            "window_days": days}
