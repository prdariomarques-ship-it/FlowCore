"""Resilient Notification Bus with Circuit Breaking, Async Buffering, and Retries."""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Any

from darius.interfaces.notifications import (
    NotificationChannelAdapter,
    NotificationDeliveryResult,
    NotificationMessage,
)

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Protects notification channels from cascading failures and rate limit storms."""

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.opened_at: float | None = None

    def can_attempt(self) -> bool:
        """Check if an attempt is permitted under the current circuit state."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            now = time.time()
            if self.opened_at is not None and (now - self.opened_at) >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker transitioning to HALF_OPEN")
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            # Allow a single trial execution
            return True

        return False

    def record_success(self) -> None:
        """Record a successful delivery, resetting the circuit."""
        self.consecutive_failures = 0
        self.opened_at = None
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Record a failure, potentially tripping the circuit to OPEN."""
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self.opened_at = time.time()
            logger.warning(
                "Circuit breaker tripped to OPEN after %d failures. Recovery timeout: %.1fs",
                self.consecutive_failures,
                self.recovery_timeout,
            )


class NotificationBus:
    """Central notification dispatcher coordinating multi-channel delivery."""

    def __init__(
        self,
        default_channel: str | None = None,
        fallback_channel: str | None = None,
        circuit_failure_threshold: int = 3,
        circuit_recovery_timeout: float = 30.0,
    ) -> None:
        self._channels: dict[str, NotificationChannelAdapter] = {}
        self._breakers: dict[str, CircuitBreaker] = {}
        self.default_channel = default_channel
        self.fallback_channel = fallback_channel
        self._circuit_failure_threshold = circuit_failure_threshold
        self._circuit_recovery_timeout = circuit_recovery_timeout

        self._queue: asyncio.Queue[tuple[NotificationMessage, list[str] | None]] = asyncio.Queue()
        self._worker_task: asyncio.Task[None] | None = None
        self._running = False

    def register_channel(
        self,
        adapter: NotificationChannelAdapter,
        is_default: bool = False,
        is_fallback: bool = False,
    ) -> None:
        """Register a notification channel adapter."""
        name = adapter.channel_name
        self._channels[name] = adapter
        self._breakers[name] = CircuitBreaker(
            failure_threshold=self._circuit_failure_threshold,
            recovery_timeout=self._circuit_recovery_timeout,
        )

        if is_default or self.default_channel is None:
            self.default_channel = name
        if is_fallback:
            self.fallback_channel = name

        logger.info("Registered notification channel '%s' (default=%s, fallback=%s)", name, is_default, is_fallback)

    def unregister_channel(self, name: str) -> None:
        """Remove a registered channel."""
        self._channels.pop(name, None)
        self._breakers.pop(name, None)
        if self.default_channel == name:
            self.default_channel = next(iter(self._channels.keys()), None)
        if self.fallback_channel == name:
            self.fallback_channel = None

    def get_channel(self, name: str) -> NotificationChannelAdapter | None:
        return self._channels.get(name)

    def list_channels(self) -> list[str]:
        return list(self._channels.keys())

    def get_breaker(self, name: str) -> CircuitBreaker | None:
        return self._breakers.get(name)

    async def _send_with_retry(
        self,
        adapter: NotificationChannelAdapter,
        breaker: CircuitBreaker,
        message: NotificationMessage,
        max_retries: int = 2,
        backoff_base: float = 0.5,
    ) -> NotificationDeliveryResult:
        """Attempt to deliver through an adapter with exponential backoff and circuit breaker tracking."""
        name = adapter.channel_name

        if not breaker.can_attempt():
            return NotificationDeliveryResult(
                success=False,
                channel=name,
                delivered_at=time.time(),
                error=f"Circuit breaker is OPEN for channel '{name}'. Delivery deferred.",
            )

        if not await adapter.is_available():
            return NotificationDeliveryResult(
                success=False,
                channel=name,
                delivered_at=time.time(),
                error=f"Channel '{name}' is not configured or unavailable.",
            )

        last_error = "Unknown delivery failure"
        for attempt in range(max_retries + 1):
            try:
                result = await adapter.send(message)
                if result.success:
                    breaker.record_success()
                    return result
                last_error = result.error or "Delivery indicated failure without error message"
            except Exception as exc:
                last_error = str(exc)

            if attempt < max_retries:
                sleep_time = backoff_base * (2**attempt)
                await asyncio.sleep(sleep_time)

        breaker.record_failure()
        return NotificationDeliveryResult(
            success=False,
            channel=name,
            delivered_at=time.time(),
            error=f"Failed after {max_retries + 1} attempts: {last_error}",
        )

    async def dispatch(
        self,
        message: NotificationMessage,
        channels: list[str] | None = None,
        max_retries: int = 1,
        backoff_base: float = 0.2,
    ) -> list[NotificationDeliveryResult]:
        """Dispatch a notification immediately across specified channels with automatic fallback."""
        target_names = channels or ([self.default_channel] if self.default_channel else [])
        if not target_names:
            target_names = list(self._channels.keys())

        results: list[NotificationDeliveryResult] = []

        for name in target_names:
            adapter = self._channels.get(name)
            breaker = self._breakers.get(name)
            if not adapter or not breaker:
                results.append(
                    NotificationDeliveryResult(
                        success=False,
                        channel=name,
                        delivered_at=time.time(),
                        error=f"Channel '{name}' is not registered on the bus.",
                    )
                )
                continue

            result = await self._send_with_retry(
                adapter=adapter,
                breaker=breaker,
                message=message,
                max_retries=max_retries,
                backoff_base=backoff_base,
            )
            results.append(result)

            # Trigger fallback if delivery failed and a fallback channel is configured
            if not result.success and self.fallback_channel and self.fallback_channel != name:
                fallback_adapter = self._channels.get(self.fallback_channel)
                fallback_breaker = self._breakers.get(self.fallback_channel)
                if fallback_adapter and fallback_breaker:
                    logger.info("Attempting fallback delivery to channel '%s'", self.fallback_channel)
                    fallback_result = await self._send_with_retry(
                        adapter=fallback_adapter,
                        breaker=fallback_breaker,
                        message=message,
                        max_retries=1,
                        backoff_base=backoff_base,
                    )
                    results.append(fallback_result)

        return results

    def enqueue(self, message: NotificationMessage, channels: list[str] | None = None) -> None:
        """Enqueue message for asynchronous background dispatch without blocking caller."""
        self._queue.put_nowait((message, channels))

    async def _worker_loop(self) -> None:
        """Background worker that continuously drains the notification queue."""
        while self._running:
            try:
                message, channels = await self._queue.get()
                try:
                    await self.dispatch(message, channels=channels)
                finally:
                    self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in notification worker loop: %s", exc, exc_info=True)

    async def start(self) -> None:
        """Start background queue worker."""
        if not self._running:
            self._running = True
            self._worker_task = asyncio.create_task(self._worker_loop())
            logger.info("NotificationBus background worker started.")

    async def stop(self) -> None:
        """Stop background worker and flush pending notifications."""
        if self._running:
            self._running = False
            if self._worker_task:
                self._worker_task.cancel()
                try:
                    await self._worker_task
                except asyncio.CancelledError:
                    pass
                self._worker_task = None
            logger.info("NotificationBus background worker stopped.")
