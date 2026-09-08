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

import html
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


# ── Daily market briefing ──────────────────────────────────────────────────────
# Full digest (curve/FX/equities/regime/news) sent to the general
# TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID — distinct from the focused B3
# summary feed below.

_REGIME_LABELS = {
    "elevated": "⚠️ ELEVADO",
    "depressed": "📉 DEPRIMIDO",
    "neutral": "➖ NEUTRO",
    "insufficient_data": "❔ SEM DADOS",
}


def build_briefing_message() -> str:
    """Compose the daily briefing: build_briefing()'s deterministic market
    lines, a regime section with emoji-coded status per dimension, and
    top news of the day — real data only, HTML-escaped for safe embedding."""
    from runtime.market_intelligence.briefing import build_briefing

    briefing = build_briefing()
    lines = ["🇧🇷 <b>DARIO OS — RADAR DE MERCADO</b>", ""]
    lines.extend(line for line in briefing.get("lines", []) if not line.startswith("REGIME:"))

    try:
        from runtime.asyncio_utils import run_sync
        from runtime.macro_score.engine import MacroScoreEngine
        from runtime.regime.engine import RegimeEngine
        from storage import EventRepository

        engine = RegimeEngine(MacroScoreEngine(EventRepository()))
        signals = run_sync(engine.classify_all())
        if signals:
            lines.append("")
            for signal in signals:
                label = signal.dimension.replace("_", " ").title()
                status = _REGIME_LABELS.get(signal.regime, signal.regime.upper())
                lines.append(f"{label}: {status}")
    except Exception:
        pass

    try:
        from runtime.market_intelligence.news import fetch_news

        items = fetch_news(max_per_group=2).get("items", [])
        if items:
            lines.append("")
            lines.append("<b>NOTÍCIAS DO DIA</b>")
            for item in items:
                lines.append(f"• {_escape(item['title'])}")
    except Exception:
        pass

    return "\n".join(lines)[:4095]


def send_briefing() -> dict[str, Any]:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise TelegramNotConfiguredError("TELEGRAM_BOT_TOKEN not set. Add the spcx-monitor bot's token to .env.")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        raise TelegramNotConfiguredError(
            "TELEGRAM_CHAT_ID not set. Add the spcx-monitor chat id to .env."
        )
    text = build_briefing_message()
    return _call("sendMessage", token, {"chat_id": chat_id, "text": text, "parse_mode": "HTML"})


# ── B3/Ibovespa summary feed ──────────────────────────────────────────────────
# Separate, focused feed sent to a dedicated bot/chat (@dariozcodebot) rather
# than the general TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID — B3 subscribers get
# only this, not the full daily briefing.


def _escape(text: str) -> str:
    """Escape text for safe embedding in a Telegram HTML-parse-mode message."""
    return html.escape(text, quote=False)


def _fmt_index_value(value: float) -> str:
    """166934.2 -> '166.934' (Brazilian thousands separator, no decimals)."""
    return f"{round(value):,}".replace(",", ".")


def _fmt_delta_pct(delta: float | None) -> str:
    if delta is None:
        return "sem variação disponível"
    return f"{delta:+.2f}%"


def build_b3_summary_message() -> str:
    """Compose the B3/Ibovespa summary — real data only, explicit when a
    source has no value or no delta rather than omitting or faking one."""
    from runtime.market_intelligence.asset_classes import analyze_asset_classes
    from runtime.market_intelligence.fx_analysis import analyze_fx

    equities = analyze_asset_classes().get("classes", {}).get("equities", {})
    ibov = next((s for s in equities.get("sources", []) if s.get("source") == "ibovespa"), None)

    fx_pairs = analyze_fx().get("pairs", [])
    usdbrl = next((p for p in fx_pairs if p.get("source") == "dollar"), None)

    lines = ["🇧🇷 <b>DARIO OS — RADAR B3</b>", ""]

    if ibov and ibov.get("value") is not None:
        lines.append(
            f"📊 <b>IBOVESPA</b>: {_fmt_index_value(ibov['value'])} pts "
            f"({_fmt_delta_pct(ibov.get('delta'))})"
        )
    else:
        lines.append("📊 <b>IBOVESPA</b>: sem dados no momento")

    if usdbrl and usdbrl.get("level") is not None:
        lines.append(
            f"💵 <b>USD/BRL</b>: R$ {usdbrl['level']:.4f} "
            f"({_fmt_delta_pct(usdbrl.get('delta_pct_1d'))})"
        )
    else:
        lines.append("💵 <b>USD/BRL</b>: sem dados no momento")

    return "\n".join(lines)[:4095]


def send_b3_summary() -> dict[str, Any]:
    token = os.getenv("TELEGRAM_BOT_TOKEN_B3")
    if not token:
        raise TelegramNotConfiguredError(
            "TELEGRAM_BOT_TOKEN_B3 not set. Add the B3/Ibovespa feed's bot token to .env."
        )
    chat_id = os.getenv("TELEGRAM_CHAT_ID_B3")
    if not chat_id:
        raise TelegramNotConfiguredError(
            "TELEGRAM_CHAT_ID_B3 not set. Add the B3/Ibovespa feed's chat id to .env."
        )
    text = build_b3_summary_message()
    return _call("sendMessage", token, {"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
