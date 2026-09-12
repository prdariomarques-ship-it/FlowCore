"""In-memory Mock Notification Channel Adapter for testing and fallback."""

from __future__ import annotations

import time
from typing import Any

from darius.interfaces.notifications import (
    NotificationChannelAdapter,
    NotificationDeliveryResult,
    NotificationMessage,
)


class MockNotificationAdapter:
    """In-memory notification adapter that captures sent messages for assertions."""

    def __init__(
        self,
        channel_name: str = "mock",
        is_available: bool = True,
        simulate_failure: bool = False,
        failure_error: str = "Simulated delivery failure",
    ) -> None:
        self._channel_name = channel_name
        self._is_available = is_available
        self.simulate_failure = simulate_failure
        self.failure_error = failure_error
        self.delivered_messages: list[NotificationMessage] = []
        self.delivery_history: list[NotificationDeliveryResult] = []

    @property
    def channel_name(self) -> str:
        return self._channel_name

    async def is_available(self) -> bool:
        return self._is_available

    def set_available(self, available: bool) -> None:
        self._is_available = available

    async def send(self, message: NotificationMessage) -> NotificationDeliveryResult:
        if not self._is_available:
            result = NotificationDeliveryResult(
                success=False,
                channel=self.channel_name,
                delivered_at=time.time(),
                error=f"Channel {self.channel_name} is currently unavailable",
            )
            self.delivery_history.append(result)
            return result

        if self.simulate_failure:
            result = NotificationDeliveryResult(
                success=False,
                channel=self.channel_name,
                delivered_at=time.time(),
                error=self.failure_error,
            )
            self.delivery_history.append(result)
            return result

        self.delivered_messages.append(message)
        result = NotificationDeliveryResult(
            success=True,
            channel=self.channel_name,
            delivered_at=time.time(),
            message_id=f"mock-{len(self.delivered_messages)}",
        )
        self.delivery_history.append(result)
        return result

    def clear(self) -> None:
        self.delivered_messages.clear()
        self.delivery_history.clear()
