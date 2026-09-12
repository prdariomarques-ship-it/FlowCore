"""Daily market briefing — composed from real observer/regime/macro data.

No LLM required: deterministic text from live numbers (treasuries, FX,
equities, commodities, VIX, regime classification). The LLM can later
polish it via /api/ask if available, but the briefing works standalone.
"""

from __future__ import annotations

from datetime import UTC, datetime

from runtime.asyncio_utils import run_sync
from runtime.macro_score.engine import MacroScoreEngine
from runtime.market_intelligence.asset_classes import analyze_asset_classes
from runtime.market_intelligence.fx_analysis import analyze_fx
from runtime.market_intelligence.yield_curve import build_yield_curve
from runtime.regime.engine import RegimeEngine
from storage import EventRepository


def build_briefing() -> dict:
    curve = build_yield_curve()
    fx = analyze_fx()
    classes = analyze_asset_classes()
    try:
        engine = RegimeEngine(MacroScoreEngine(EventRepository()))
        signals = run_sync(engine.classify_all())
        regime = {s.dimension: {"status": s.regime, "score": s.score} for s in signals}
    except Exception:
        regime = None
    lines: list[str] = []
    lines.append(f"CURVA EUA: {curve.state}"
                 + (f" (10Y-2Y {curve.slope_10y_2y} bps)" if curve.slope_10y_2y is not None else ""))
    if curve.shape:
        lines.append(f"  formato: {curve.shape}"
                     + (f" — {curve.interpretation}" if curve.interpretation else ""))
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
        if movers:
            hl = ", ".join("{} {:+.1f}{}".format(s["source"], s["delta"], s["delta_unit"])
                           for s in movers)
            lines.append(f"{cls['name'].upper()}: {len(cls['sources'])} fontes | destaques: {hl}")
        else:
            lines.append(f"{cls['name'].upper()}: {len(cls['sources'])} fontes")
    if regime:
        dims = [f"{k}={v.get('status', v)}" for k, v in regime.items()] if isinstance(regime, dict) else []
        if dims:
            lines.append("REGIME: " + " | ".join(dims))

    # Score history context (trend D-5 → atual), honesto: só quando existe
    try:
        from runtime.market_intelligence.score_history import score_history
        hist = score_history()
        for dim, view in hist.get("windows", {}).items():
            latest = view.get("latest")
            d5 = view.get("history", {}).get("D-5", {})
            if latest and latest.get("value") is not None:
                d5v = d5.get("value")
                trend = ("estável" if d5v is None else
                         ("subindo" if latest["value"] > d5v else "caindo"))
                lines.append(f"MACRO {dim.upper()}: {latest['value']:+.2f} "
                             f"({latest['status']}) | tendência D-5: {trend}")
    except Exception:  # noqa: BLE001 — briefing nunca falha por dependência
        pass

    # Top news do dia (categorias, sem recontar títulos)
    try:
        from runtime.market_intelligence.news import fetch_news
        news = fetch_news(max_per_group=2)
        cats = sorted({it["category"] for it in news["items"]})
        n = len(news["items"])
        lines.append(f"NOTÍCIAS: {n} itens recentes | "
                     + (f"categorias: {', '.join(cats)}" if cats else "sem itens"))
    except Exception:  # noqa: BLE001
        lines.append("NOTÍCIAS: indisponível")

    # Alertas ativos do dia
    try:
        from runtime.market_intelligence.alerts import list_alerts
        alerts = list_alerts(limit=3)
        if alerts:
            lines.append("ALERTAS: " + ", ".join(a["label"] for a in alerts))
    except Exception:  # noqa: BLE001
        pass

    return {"lines": lines, "generated_at": datetime.now(UTC).isoformat()}


def fmt(v):
    return f"{v:+.2f}" if v is not None else "—"
