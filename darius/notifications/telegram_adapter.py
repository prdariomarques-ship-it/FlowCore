"""Telegram Notification Channel Adapter for DARIUS OSS.

Wraps runtime.telegram.send_message inside a non-blocking asynchronous adapter,
preventing network latency or Telegram API throttling from freezing the main event loop.
"""

from __future__ import annotations

import asyncio
import html
import time
from typing import Any

from darius.interfaces.notifications import (
    NotificationChannelAdapter,
    NotificationDeliveryResult,
    NotificationMessage,
)


class TelegramNotificationAdapter:
    """Non-blocking Telegram adapter conforming to NotificationChannelAdapter."""

    LEVEL_PREFIXES = {
        "INFO": "ℹ️",
        "WARNING": "⚠️",
        "CRITICAL": "🚨",
    }

    def __init__(
        self,
        default_chat_id: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._default_chat_id = default_chat_id
        self._timeout = timeout

    @property
    def channel_name(self) -> str:
        return "telegram"

    async def is_available(self) -> bool:
        """Non-blocking availability check using environment configuration."""
        try:
            from runtime.telegram import get_configuration

            cfg = get_configuration()
            # If default_chat_id was provided at init, we only need the token configured
            if self._default_chat_id and cfg.get("token_set"):
                return True
            return bool(cfg.get("configured"))
        except Exception:
            return False

    def _format_payload(self, message: NotificationMessage) -> str:
        """Format notification title, body, and metadata for Telegram."""
        icon = self.LEVEL_PREFIXES.get(message.level, "ℹ️")
        escaped_title = html.escape(message.title, quote=False)
        escaped_body = html.escape(message.body, quote=False)

        lines = [f"{icon} <b>{escaped_title}</b>", "", escaped_body]

        if message.metadata:
            meta_lines = []
            for k, v in message.metadata.items():
                if k not in ("chat_id", "parse_mode", "raw"):
                    meta_lines.append(f"• <i>{html.escape(str(k))}:</i> {html.escape(str(v))}")
            if meta_lines:
                lines.append("")
                lines.extend(meta_lines)

        return "\n".join(lines)[:4095]

    async def send(self, message: NotificationMessage) -> NotificationDeliveryResult:
        """Send notification asynchronously via thread pool to prevent loop blocking."""
        recipient = message.recipient or message.metadata.get("chat_id") or self._default_chat_id

        payload = self._format_payload(message)

        def _sync_send() -> dict[str, Any]:
            from runtime.telegram import send_message

            return send_message(text=payload, chat_id=recipient, timeout=self._timeout)

        try:
            # Delegate blocking urllib network I/O to worker thread
            resp = await asyncio.to_thread(_sync_send)
            message_id = str(resp.get("message_id")) if isinstance(resp, dict) and "message_id" in resp else None
            return NotificationDeliveryResult(
                success=True,
                channel=self.channel_name,
                delivered_at=time.time(),
                message_id=message_id,
            )
        except Exception as exc:
            return NotificationDeliveryResult(
                success=False,
                channel=self.channel_name,
                delivered_at=time.time(),
                error=f"Telegram delivery failed: {exc}",
            )
