"""DARIUS OSS Notification Subsystem.

Provides decoupled, resilient, and non-blocking notification channels,
circuit breakers, background queues, and channel adapters.
"""

from __future__ import annotations

from darius.notifications.bus import CircuitBreaker, CircuitState, NotificationBus
from darius.notifications.mock_adapter import MockNotificationAdapter
from darius.notifications.telegram_adapter import TelegramNotificationAdapter

__all__ = [
    "CircuitBreaker",
    "CircuitState",
    "NotificationBus",
    "TelegramNotificationAdapter",
    "MockNotificationAdapter",
]
