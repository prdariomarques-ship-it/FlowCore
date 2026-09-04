"""Brief Diário — morning intelligence digest for FlowCore.

Pipeline:
1. Collect raw market data (yield curve, FX, regime, macro-score, news, alerts)
2. Format into structured sections
3. Optionally polish with LLM (if Ollama available) — keeps original if LLM fails
4. Return structured dict + plain-text Telegram message
5. Optionally send to Telegram

Deterministic path never fails. LLM polish is always optional.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_BRIEF_CACHE = Path.home() / ".flowcore" / "last_brief.json"
_BRIEF_HISTORY = Path.home() / ".flowcore" / "brief_history.json"


# ── formatters ────────────────────────────────────────────────────────────────

def _fmt(v: Any, decimals: int = 2, unit: str = "") -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):+.{decimals}f}{unit}"
    except (TypeError, ValueError):
        return str(v)


def _arrow(v: Any) -> str:
    if v is None:
        return ""
    try:
        return " ↑" if float(v) > 0 else (" ↓" if float(v) < 0 else " →")
    except (TypeError, ValueError):
        return ""


# ── section collectors ────────────────────────────────────────────────────────

def _section_macro() -> dict[str, Any]:
    try:
        from runtime.market_intelligence.score_history import score_history
        hist = score_history()
        dims = []
        for dim, view in hist.get("windows", {}).items():
            latest = view.get("latest", {})
            d5 = view.get("history", {}).get("D-5", {})
            val = latest.get("value")
            d5v = d5.get("value")
            trend = "→" if d5v is None else ("↑" if val and val > d5v else "↓")
            dims.append({
                "dimension": dim,
                "value": val,
                "status": latest.get("status", ""),
                "trend": trend,
            })
        return {"ok": True, "dimensions": dims}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "dimensions": []}


def _section_regime() -> dict[str, Any]:
    try:
        from runtime.regime.engine import RegimeEngine
        regime = RegimeEngine().classify_all()
        signals = []
        if isinstance(regime, dict):
            for k, v in regime.items():
                if isinstance(v, dict):
                    signals.append({"name": k, "status": v.get("status", ""), "value": v.get("value")})
                else:
                    signals.append({"name": k, "status": str(v)})
        return {"ok": True, "signals": signals}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "signals": []}


def _section_fx() -> dict[str, Any]:
    try:
        from runtime.market_intelligence.fx_analysis import analyze_fx
        fx = analyze_fx()
        return {"ok": True, "dxy_delta": fx.get("dxy_delta_pct_1d"), "pairs": fx.get("pairs", []), "regime": fx.get("usd_regime", "")}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "dxy_delta": None, "pairs": []}


def _section_yield() -> dict[str, Any]:
    try:
        from runtime.market_intelligence.yield_curve import build_yield_curve
        curve = build_yield_curve()
        return {
            "ok": True,
            "state": curve.state,
            "shape": curve.shape,
            "slope_10y_2y": curve.slope_10y_2y,
            "interpretation": curve.interpretation,
            "points": [{"label": p.label, "yield_pct": p.yield_pct} for p in curve.points if p.yield_pct is not None],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "state": "unavailable", "points": []}


def _section_news() -> dict[str, Any]:
    try:
        from runtime.market_intelligence.news import fetch_news
        result = fetch_news(max_per_group=3, section="all")
        items = result.get("items", [])
        categories = sorted({i["category"] for i in items})
        top = [{"headline": i["headline"], "category": i["category"], "publisher": i.get("publisher", "")} for i in items[:5]]
        return {"ok": True, "total": len(items), "categories": categories, "top": top}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "total": 0, "top": []}


def _section_alerts() -> dict[str, Any]:
    try:
        from runtime.market_intelligence.alerts import list_alerts
        alerts = list_alerts(limit=5)
        return {"ok": True, "alerts": alerts}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "alerts": []}


# ── LLM polish ────────────────────────────────────────────────────────────────

def _polish_with_llm(raw_text: str, ollama_url: str, model: str) -> str:
    """Ask LLM to turn raw market data into a fluent morning brief in PT-BR."""
    import urllib.request
    system = (
        "Você é o analista matinal do FlowCore. Transforme os dados brutos em um "
        "parágrafo de 4-6 frases em português brasileiro, fluente e objetivo, "
        "adequado para um brief de mercado das 7h30. "
        "Preserve todos os números. Não invente dados. Não use linguagem sensacionalista."
    )
    prompt = f"Dados brutos do mercado:\n\n{raw_text}\n\nEscreva o brief matinal:"
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        f"{ollama_url.rstrip('/')}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    return data.get("message", {}).get("content", "").strip()


# ── text formatter for Telegram ───────────────────────────────────────────────

def _format_telegram(sections: dict[str, Any], llm_text: str | None, generated_at: str) -> str:
    lines: list[str] = []
    lines.append(f"📊 *BRIEF MATINAL — FlowCore*")
    lines.append(f"_{generated_at[:10]} {generated_at[11:16]} UTC_")
    lines.append("")

    if llm_text:
        lines.append(llm_text)
        lines.append("")

    # Yield curve
    y = sections["yield"]
    if y["ok"]:
        state_emoji = {"normal": "✅", "inverted": "⚠️", "flat": "➡️"}.get(y.get("state", ""), "📈")
        lines.append(f"{state_emoji} *Curva EUA*: {y.get('state', '—')} "
                     f"(10Y-2Y: {_fmt(y.get('slope_10y_2y'), 0, ' bps')})")

    # FX
    fx = sections["fx"]
    if fx["ok"]:
        lines.append(f"💱 *DXY*: {_fmt(fx.get('dxy_delta'), 2, '%')}{_arrow(fx.get('dxy_delta'))}")
        for pair in fx.get("pairs", [])[:3]:
            if pair.get("level") is not None:
                lines.append(f"  • {pair['name']}: {pair['level']:.4f} "
                             f"({_fmt(pair.get('delta_pct_1d'))}%{_arrow(pair.get('delta_pct_1d'))})")

    # Regime
    reg = sections["regime"]
    if reg["ok"] and reg["signals"]:
        statuses = " | ".join(f"{s['name']}: {s['status']}" for s in reg["signals"][:4])
        lines.append(f"🔭 *Regime*: {statuses}")

    # Macro score
    mac = sections["macro"]
    if mac["ok"] and mac["dimensions"]:
        for dim in mac["dimensions"][:3]:
            lines.append(f"📐 *Macro {dim['dimension']}*: {_fmt(dim.get('value'))} "
                         f"({dim.get('status', '')} {dim.get('trend', '')})")

    # News
    news = sections["news"]
    if news["ok"] and news["top"]:
        lines.append("")
        lines.append(f"📰 *Notícias* ({news['total']} itens | {', '.join(news['categories'][:4])})")
        for item in news["top"][:3]:
            lines.append(f"  • [{item['category']}] {item['headline'][:80]}")

    # Alerts
    alts = sections["alerts"]
    if alts["ok"] and alts["alerts"]:
        lines.append("")
        lines.append("🚨 *Alertas ativos*:")
        for a in alts["alerts"][:3]:
            lines.append(f"  • {a.get('label', a)}")

    lines.append("")
    lines.append("_FlowCore AI · via Ollama_")
    return "\n".join(lines)


# ── main entry point ──────────────────────────────────────────────────────────

def build_brief(
    *,
    use_llm: bool = True,
    ollama_url: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Build the full morning brief. Returns structured dict + telegram_text."""
    generated_at = datetime.now(timezone.utc).isoformat()

    sections = {
        "yield": _section_yield(),
        "fx": _section_fx(),
        "regime": _section_regime(),
        "macro": _section_macro(),
        "news": _section_news(),
        "alerts": _section_alerts(),
    }

    # Raw text for LLM input
    raw_lines: list[str] = []
    y = sections["yield"]
    if y["ok"]:
        raw_lines.append(f"Curva EUA: {y.get('state')} (inclinação 10Y-2Y: {y.get('slope_10y_2y')} bps)")
    fx = sections["fx"]
    if fx["ok"]:
        raw_lines.append(f"DXY: {_fmt(fx.get('dxy_delta'))}%")
        for pair in fx.get("pairs", [])[:3]:
            if pair.get("level"):
                raw_lines.append(f"{pair['name']}: {pair['level']:.4f} ({_fmt(pair.get('delta_pct_1d'))}%)")
    mac = sections["macro"]
    for dim in mac.get("dimensions", []):
        raw_lines.append(f"Macro {dim['dimension']}: {_fmt(dim.get('value'))} ({dim.get('status', '')})")
    news = sections["news"]
    if news["ok"]:
        raw_lines.append(f"Notícias: {news['total']} itens, categorias: {', '.join(news.get('categories', []))}")

    llm_text: str | None = None
    llm_error: str | None = None
    if use_llm and raw_lines:
        try:
            cfg_path = Path.home() / ".flowcore" / "ai.json"
            cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
            url = ollama_url or cfg.get("ollama_url", "http://localhost:11434")
            mdl = model or cfg.get("model", "")
            if url and mdl:
                llm_text = _polish_with_llm("\n".join(raw_lines), url, mdl)
        except Exception as exc:
            llm_error = str(exc)

    telegram_text = _format_telegram(sections, llm_text, generated_at)

    result: dict[str, Any] = {
        "generated_at": generated_at,
        "sections": sections,
        "llm_polish": llm_text,
        "llm_error": llm_error,
        "telegram_text": telegram_text,
        "raw_lines": raw_lines,
    }

    # Cache last brief
    try:
        _BRIEF_CACHE.parent.mkdir(parents=True, exist_ok=True)
        _BRIEF_CACHE.write_text(json.dumps(result, ensure_ascii=False, default=str))
    except Exception:
        pass

    # Append to rolling history (keep 30 days)
    try:
        history = json.loads(_BRIEF_HISTORY.read_text()) if _BRIEF_HISTORY.exists() else []
        history.append({"generated_at": generated_at, "llm_polish": llm_text, "raw_lines": raw_lines})
        _BRIEF_HISTORY.write_text(json.dumps(history[-30:], ensure_ascii=False, default=str))
    except Exception:
        pass

    # Sync to Obsidian vault (silent — never blocks brief delivery)
    try:
        from runtime.obsidian import ObsidianSync
        obsidian_result = ObsidianSync().write_brief(result)
        result["obsidian"] = obsidian_result
    except Exception as exc:
        result["obsidian"] = {"written": False, "reason": str(exc)}

    return result


def get_last_brief() -> dict[str, Any] | None:
    """Return the last generated brief from cache."""
    if _BRIEF_CACHE.exists():
        try:
            return json.loads(_BRIEF_CACHE.read_text())
        except Exception:
            pass
    return None


def send_brief_to_telegram(brief: dict[str, Any]) -> bool:
    """Send the telegram_text to the configured Telegram channel. Returns True on success."""
    try:
        from runtime.telegram import send_message
        send_message(brief["telegram_text"])
        return True
    except Exception:
        return False
