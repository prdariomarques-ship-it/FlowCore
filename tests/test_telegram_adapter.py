"""Tests for Telegram Adapter."""

import pytest
from runtime.channels.telegram_adapter import get_telegram_adapter
from runtime.events.schemas import Event, EventPriority

def test_telegram_adapter():
    adapter = get_telegram_adapter()

    ans = adapter.handle_natural_language_query("Quem precisa da minha atenção hoje?")
    assert isinstance(ans, str)
    assert len(ans) > 0

    evt = Event(type="CLIENT_WITHDRAWAL", source="test", entity="cli_001", payload={"amount": 100000}, priority=EventPriority.CRITICAL)
    res = adapter.notify_proactive_alert(evt)
    assert res["status"] == "DELIVERED"
