"""FlowCore — Telegram integration (Sprint 17, Milestone 4).

Reuses the user's existing spcx-monitor Telegram bot (already running,
sending real financial alerts) rather than a new dedicated bot — confirmed
with the user. FlowCore's notifications land in the same chat as
spcx-monitor/signal-engine/renda-fixa-monitor's alerts.

Outbound send only — no webhook, no long-polling for inbound commands,
matching how the user's existing bots are actually used (alerting, not
command handling). Stdlib-only (urllib), matching runtime/ollama.py's
style — no new dependency for a simple bearer-token-style API.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramError(RuntimeError):
    """Base class for all Telegram errors raised by FlowCore."""


class TelegramNotConfiguredError(TelegramError):
    """TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set."""


def _call(method: str, token: str, body: dict[str, Any] | None = None, timeout: float = 10) -> dict[str, Any]:
    url = f"{TELEGRAM_API_BASE}/bot{token}/{method}"
    req = None
    if body is not None:
        req = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST"
        )
    try:
        with urllib.request.urlopen(req or url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        raise TelegramError(f"Telegram API error {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise TelegramError(f"Telegram unreachable: {e}") from e
    if not data.get("ok"):
        raise TelegramError(f"Telegram API error: {data}")
    return data["result"]


def get_configuration() -> dict[str, Any]:
    """Static check — no network call. Whether the env vars are set at all."""
    token_set = bool(os.getenv("TELEGRAM_BOT_TOKEN"))
    chat_id_set = bool(os.getenv("TELEGRAM_CHAT_ID"))
    return {"configured": token_set and chat_id_set, "token_set": token_set, "chat_id_set": chat_id_set}


def check_health() -> dict[str, Any]:
    """Is the bot token valid? Calls Telegram's getMe endpoint (real network call)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise TelegramNotConfiguredError("TELEGRAM_BOT_TOKEN not set. Add the spcx-monitor bot's token to .env.")
    return _call("getMe", token)


def _escape(text: str) -> str:
    """Escape text for Telegram HTML parse mode."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _score_trend_line(score: float | None, status: str) -> str:
    """Numeric score + trend arrow for a dimension."""
    if score is None:
        return "sem pontuação"
    if status == "elevated":
        arrow = "▲"
    elif status == "depressed":
        arrow = "▼"
    else:
        arrow = "◆"
    return f"{arrow} {score:+.2f}"


def build_briefing_message() -> str:
    """Compose a rich HTML briefing from real market data (SPC-X/SML digest format).

    Includes: headline date, US yield curve with slope, FX (DXY + pairs with regime),
    asset classes with movers, macro regime (SCPX), macro-score trends and market
    news/alert counts. Telegram supports HTML with a 4096-char limit — sections are
    capped to stay under it; HTML escaping is applied to all free text.
    """
    from runtime.market_intelligence.briefing import build_briefing
    from runtime.market_intelligence.news import fetch_news
    from runtime.regime.engine import RegimeEngine

    b = build_briefing()
    lines = b["lines"]
    if not lines:
        lines = ["Mercado: sem dados suficientes no momento."]

    # Headline com status do regime
    try:
        regime = RegimeEngine().classify_all()
    except Exception:
        regime = None
    status_map = {
        "elevated": "⚠️ ELEVADO",
        "depressed": "📉 DEPRIMIDO",
        "neutral": "➖ NEUTRO",
        "bullish": "📈 ALTA",
        "bearish": "📉 BAIXA",
        "insufficient_data": "❓ SEM DADOS",
    }
    def status_label(v: str | dict) -> str:
        if isinstance(v, dict):
            v = v.get("status", v.get("regime", ""))
        return str(status_map.get(str(v), str(v).upper()))

    headline = "📊 <b>DARIO OS — RADAR DE MERCADO</b>"
    if regime and isinstance(regime, dict):
        labels = []
        for dim in ("commodities", "liquidity", "risk_sentiment"):
            if dim in regime:
                sig = regime[dim]
                score = sig.get("score") if isinstance(sig, dict) else None
                labels.append(
                    f"{dim.replace('_', ' ').title()}: {status_label(sig)} "
                    f"({_score_trend_line(score, str(sig.get('regime', ''))) if isinstance(sig, dict) else ''})"
                )
        if labels:
            headline += "\n⚖️ <b>REGIME SCPX:</b>\n" + "\n".join(labels)

    # Corpo: só as linhas principais, sem pontos internos para caber no limite
    body_parts: list[str] = [headline, ""]
    for line in lines[:22]:  # margem de segurança dentro dos 4096 chars
        if not line:
            continue
        line = _escape(line)
        line = line.replace("|", "·")
        if line.startswith("  "):
            line = "─ " + line.strip()
        body_parts.append(line)

    # Seção de tendências históricas (D-1/D-5/D-20) por dimensão — nunca interpolada
    try:
        from runtime.market_intelligence.score_history import score_history

        hist = score_history(days=20)
        hist_lines: list[str] = []
        if hist and isinstance(hist, dict):
            windows = hist.get("windows") or {}
            for dim, wdata in windows.items():
                if not isinstance(wdata, dict):
                    continue
                views = wdata.get("history") or {}
                parts = []
                for window in ("D-1", "D-5", "D-20"):
                    v = views.get(window)
                    if not isinstance(v, dict):
                        continue
                    val = v.get("value")
                    if val is not None:
                        parts.append(f"{window}: {float(val):+.2f} ({_escape(str(v.get('status', '')))})")
                if parts:
                    hist_lines.append(f"▪ {dim.replace('_', ' ').title()}: " + " · ".join(parts))
        if hist_lines:
            body_parts.append("")
            body_parts.append("📈 <b>HISTÓRICO SCPX (DADOS REAIS)</b>")
            body_parts.extend(hist_lines[:3])
    except Exception:  # noqa: BLE001
        pass

    # Notícias do dia em uma seção própria (títulos, não apenas contagem)
    news_section: list[str] = []
    try:
        news = fetch_news(max_per_group=2)
        if news.get("items"):
            news_section.append("")
            news_section.append("🗞️ <b>NOTÍCIAS DO DIA</b>")
            for it in news["items"][:10]:
                cat = _escape(it.get("category", "")).upper()[:24]
                title = _escape(it.get("title", ""))[:95]
                news_section.append(f"• <b>[{cat}]</b> {title}")
    except Exception:  # noqa: BLE001
        pass

    msg = "\n".join(body_parts + news_section)
    return msg[:4095]


def send_briefing(chat_id: str | None = None, timeout: float = 15) -> dict[str, Any]:
    """Send the rich daily briefing (HTML) to the configured chat."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise TelegramNotConfiguredError("TELEGRAM_BOT_TOKEN not set. Add the spcx-monitor bot's token to .env.")
    resolved_chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if not resolved_chat_id:
        raise TelegramNotConfiguredError("chat_id not provided and TELEGRAM_CHAT_ID not set.")
    return _call(
        "sendMessage",
        token,
        {"chat_id": resolved_chat_id, "text": build_briefing_message(), "parse_mode": "HTML"},
        timeout=timeout,
    )


def send_message(text: str, chat_id: str | None = None, timeout: float = 10) -> dict[str, Any]:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise TelegramNotConfiguredError("TELEGRAM_BOT_TOKEN not set. Add the spcx-monitor bot's token to .env.")
    resolved_chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if not resolved_chat_id:
        raise TelegramNotConfiguredError(
            "chat_id not provided and TELEGRAM_CHAT_ID not set. Add the spcx-monitor chat id to .env "
            "or pass chat_id explicitly."
        )
    return _call("sendMessage", token, {"chat_id": resolved_chat_id, "text": text}, timeout=timeout)
