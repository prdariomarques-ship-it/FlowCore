"""Daily market briefing — composed from real observer/regime/macro data.

No LLM required: deterministic text from live numbers (treasuries, FX,
equities, commodities, VIX, regime classification). The LLM can later
polish it via /api/ask if available, but the briefing works standalone.
"""

from __future__ import annotations

from runtime.market_intelligence.asset_classes import analyze_asset_classes
from runtime.market_intelligence.fx_analysis import analyze_fx
from runtime.market_intelligence.yield_curve import build_yield_curve
from runtime.regime.engine import RegimeEngine


def build_briefing() -> dict:
    curve = build_yield_curve()
    fx = analyze_fx()
    classes = analyze_asset_classes()
    try:
        regime = RegimeEngine().classify_all()
    except Exception:
        regime = None
    lines: list[str] = []
    lines.append(f"CURVA EUA: {curve.state}"
                 + (f" (10Y-2Y {curve.slope_10y_2y} bps)" if curve.slope_10y_2y is not None else ""))
    for p in curve.points:
        if p.yield_pct is not None:
            lines.append(f"  {p.label}: {p.yield_pct}%")
    lines.append(f"DÓLAR: DXY {fmt(fx['dxy_delta_pct_1d'])}% no dia")
    for pair in fx["pairs"]:
        if pair["level"] is not None:
            lines.append(f"  {pair['name']}: {pair['level']:.4f} ({fmt(pair['delta_pct_1d'])}%) "
                         f"[USD {pair['usd_regime']}]")
    for cls_name, cls in classes["classes"].items():
        movers = [s for s in cls["sources"]
                  if s.get("delta") is not None and abs(s["delta"] or 0) >= 1]
        lines.append(f"{cls['name'].upper()}: {len(cls['sources'])} fontes "
                     + (f"| destaques: {', '.join(f'{s['source']} {s['delta']:.1f}{s['delta_unit']}' for s in movers)}" if movers else ""))
    if regime:
        dims = [f"{k}={v.get('status', v)}" for k, v in regime.items()] if isinstance(regime, dict) else []
        if dims:
            lines.append("REGIME: " + " | ".join(dims))
    return {"lines": lines, "generated_at": __import__("datetime", fromlist=["datetime", "UTC"]).datetime.now(__import__("datetime", fromlist=["UTC"]).UTC).isoformat()}


def fmt(v):
    return f"{v:+.2f}" if v is not None else "—"
