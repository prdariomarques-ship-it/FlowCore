"""Notification Channel Adapter Protocol and Data Models for DARIUS OSS."""

from __future__ import annotations

import time
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class NotificationMessage(BaseModel):
    """Normalized payload dispatched through notification channels."""

    title: str
    body: str
    level: Literal["INFO", "WARNING", "CRITICAL"] = "INFO"
    recipient: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NotificationDeliveryResult(BaseModel):
    """Execution status returned after attempting delivery across a channel."""

    success: bool
    channel: str
    delivered_at: float = Field(default_factory=time.time)
    error: str | None = None
    message_id: str | None = None


@runtime_checkable
class NotificationChannelAdapter(Protocol):
    """Port interface for outbound communication channels (Telegram, WhatsApp, Webhook, etc.)."""

    @property
    def channel_name(self) -> str:
        """Unique identifier representing the notification channel."""
        ...

    async def send(self, message: NotificationMessage) -> NotificationDeliveryResult:
        """Deliver a notification message via this channel."""
        ...

    async def is_available(self) -> bool:
        """Check if channel credentials and external gateway are configured and available."""
        ...
