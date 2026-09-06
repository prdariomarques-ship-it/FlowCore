"""Tests for CoreOrchestrator."""

import pytest
from runtime.events.schemas import Event, EventPriority
from runtime.events.bus import EventBus
from agents.orchestrator import get_orchestrator

@pytest.mark.asyncio
async def test_orchestrator_event_processing(tmp_path):
    storage = tmp_path / "events.json"
    bus = EventBus(storage_file=storage)
    orchestrator = get_orchestrator()

    evt = Event(
        type="PORTFOLIO_OUT_OF_PROFILE",
        source="system",
        entity="cli_100",
        payload={"diff": 10.0},
        priority=EventPriority.CRITICAL,
    )
    bus.publish(evt)

    res = await orchestrator.process_event(evt)
    assert res["orchestrated"] is True
    assert res["target_agent"] == "compliance_agent"
    assert res["status"] == "COMPLETED"
