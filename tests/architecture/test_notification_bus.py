"""Tests for NotificationBus, CircuitBreaker, TelegramAdapter, and MockAdapter."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest

from darius.interfaces.notifications import (
    NotificationChannelAdapter,
    NotificationMessage,
)
from darius.notifications.bus import (
    CircuitBreaker,
    CircuitState,
    NotificationBus,
)
from darius.notifications.mock_adapter import MockNotificationAdapter
from darius.notifications.telegram_adapter import TelegramNotificationAdapter


class TestMockNotificationAdapter:
    @pytest.mark.asyncio
    async def test_mock_send_success(self):
        adapter = MockNotificationAdapter()
        assert adapter.channel_name == "mock"
        assert await adapter.is_available()

        msg = NotificationMessage(title="Test", body="Content", level="INFO")
        result = await adapter.send(msg)
        assert result.success is True
        assert len(adapter.delivered_messages) == 1
        assert adapter.delivered_messages[0].title == "Test"

    @pytest.mark.asyncio
    async def test_mock_simulated_failure(self):
        adapter = MockNotificationAdapter(simulate_failure=True, failure_error="Simulated error")
        msg = NotificationMessage(title="Test", body="Content")
        result = await adapter.send(msg)
        assert result.success is False
        assert "Simulated error" in (result.error or "")
        assert len(adapter.delivered_messages) == 0

    @pytest.mark.asyncio
    async def test_mock_unavailable(self):
        adapter = MockNotificationAdapter(is_available=False)
        msg = NotificationMessage(title="Test", body="Content")
        result = await adapter.send(msg)
        assert result.success is False
        assert "unavailable" in (result.error or "")


class TestTelegramNotificationAdapter:
    def test_protocol_compliance(self):
        adapter = TelegramNotificationAdapter()
        assert isinstance(adapter, NotificationChannelAdapter)
        assert adapter.channel_name == "telegram"

    @pytest.mark.asyncio
    async def test_is_available_delegates_to_runtime_telegram(self):
        adapter = TelegramNotificationAdapter()
        with patch("runtime.telegram.get_configuration", return_value={"configured": True, "token_set": True}):
            assert await adapter.is_available() is True

        with patch("runtime.telegram.get_configuration", return_value={"configured": False, "token_set": False}):
            assert await adapter.is_available() is False

    def test_message_formatting(self):
        adapter = TelegramNotificationAdapter()
        msg = NotificationMessage(
            title="Market Drift",
            body="Asset drifted by 3.5%",
            level="WARNING",
            metadata={"ticker": "PETR4", "chat_id": "ignored_in_body"},
        )
        formatted = adapter._format_payload(msg)
        assert "⚠️ <b>Market Drift</b>" in formatted
        assert "Asset drifted by 3.5%" in formatted
        assert "• <i>ticker:</i> PETR4" in formatted
        # chat_id must be excluded from body text
        assert "chat_id" not in formatted

    @pytest.mark.asyncio
    async def test_send_success(self):
        adapter = TelegramNotificationAdapter(default_chat_id="default_123")
        msg = NotificationMessage(title="Alert", body="Test message", level="CRITICAL")

        with patch("runtime.telegram.send_message", return_value={"ok": True, "message_id": 9999}) as mock_send:
            result = await adapter.send(msg)
            assert result.success is True
            assert result.channel == "telegram"
            assert result.message_id == "9999"
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_catches_telegram_error_gracefully(self):
        from runtime.telegram import TelegramError

        adapter = TelegramNotificationAdapter()
        msg = NotificationMessage(title="Alert", body="Test message")

        with patch("runtime.telegram.send_message", side_effect=TelegramError("Network down")):
            result = await adapter.send(msg)
            assert result.success is False
            assert "Network down" in (result.error or "")
            assert result.channel == "telegram"


class TestCircuitBreaker:
    def test_initial_state_and_success(self):
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        assert breaker.state == CircuitState.CLOSED
        assert breaker.can_attempt() is True

        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.consecutive_failures == 0

    def test_trips_to_open_after_threshold(self):
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.can_attempt() is True

        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        assert breaker.can_attempt() is False

    def test_recovers_to_half_open_then_closed(self):
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05)
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # Immediately should reject
        assert breaker.can_attempt() is False

        # Wait recovery timeout
        time.sleep(0.06)
        # Should now allow one trial (HALF_OPEN)
        assert breaker.can_attempt() is True
        assert breaker.state == CircuitState.HALF_OPEN

        # If trial succeeds -> CLOSED
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.consecutive_failures == 0


class TestNotificationBus:
    @pytest.mark.asyncio
    async def test_register_and_dispatch(self):
        bus = NotificationBus()
        mock = MockNotificationAdapter(channel_name="mock")
        bus.register_channel(mock, is_default=True)

        assert bus.list_channels() == ["mock"]
        assert bus.get_channel("mock") is mock

        msg = NotificationMessage(title="Test", body="Hello")
        results = await bus.dispatch(msg)

        assert len(results) == 1
        assert results[0].success is True
        assert len(mock.delivered_messages) == 1

    @pytest.mark.asyncio
    async def test_fallback_delivery_on_primary_failure(self):
        bus = NotificationBus(default_channel="primary", fallback_channel="backup")

        primary = MockNotificationAdapter(channel_name="primary", simulate_failure=True)
        backup = MockNotificationAdapter(channel_name="backup")

        bus.register_channel(primary, is_default=True)
        bus.register_channel(backup, is_fallback=True)

        msg = NotificationMessage(title="Failover Alert", body="Primary channel is dead")
        results = await bus.dispatch(msg, max_retries=0)

        # Expect two results: primary failure + fallback success
        assert len(results) == 2
        assert results[0].success is False
        assert results[0].channel == "primary"
        assert results[1].success is True
        assert results[1].channel == "backup"
        assert len(backup.delivered_messages) == 1

    @pytest.mark.asyncio
    async def test_circuit_breaker_trips_in_bus(self):
        bus = NotificationBus(circuit_failure_threshold=2, circuit_recovery_timeout=10.0)
        failing_mock = MockNotificationAdapter(channel_name="flaky", simulate_failure=True)
        bus.register_channel(failing_mock, is_default=True)

        msg = NotificationMessage(title="T1", body="B1")

        # 1st dispatch -> fails, consecutive_failures = 1
        await bus.dispatch(msg, max_retries=0)
        breaker = bus.get_breaker("flaky")
        assert breaker.state == CircuitState.CLOSED

        # 2nd dispatch -> fails, consecutive_failures = 2 -> trips OPEN
        await bus.dispatch(msg, max_retries=0)
        assert breaker.state == CircuitState.OPEN

        # 3rd dispatch -> rejected immediately by circuit breaker
        results = await bus.dispatch(msg, max_retries=0)
        assert results[0].success is False
        assert "Circuit breaker is OPEN" in results[0].error

    @pytest.mark.asyncio
    async def test_async_background_worker_queue(self):
        bus = NotificationBus()
        mock = MockNotificationAdapter(channel_name="mock")
        bus.register_channel(mock, is_default=True)

        await bus.start()
        try:
            msg = NotificationMessage(title="Async Msg", body="Non-blocking execution")
            bus.enqueue(msg)

            # Wait briefly for worker loop to drain
            for _ in range(20):
                if len(mock.delivered_messages) > 0:
                    break
                await asyncio.sleep(0.05)

            assert len(mock.delivered_messages) == 1
            assert mock.delivered_messages[0].title == "Async Msg"
        finally:
            await bus.stop()
