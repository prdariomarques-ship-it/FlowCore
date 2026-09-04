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
