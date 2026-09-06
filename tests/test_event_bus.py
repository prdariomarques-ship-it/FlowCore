"""Tests for EventBus and Event Schemas."""

import pytest
import os
from pathlib import Path
from runtime.events.schemas import Event, EventPriority, EventStatus
from runtime.events.bus import EventBus

def test_event_schema():
    evt = Event(
        type="PORTFOLIO_OUT_OF_PROFILE",
        source="compliance_agent",
        entity="client_123",
        payload={"diff": 8.0},
        priority=EventPriority.HIGH,
    )
    d = evt.to_dict()
    assert d["type"] == "PORTFOLIO_OUT_OF_PROFILE"
    assert d["priority"] == "HIGH"

    reconstructed = Event.from_dict(d)
    assert reconstructed.id == evt.id
    assert reconstructed.priority == EventPriority.HIGH

def test_event_bus_publish_and_pending(tmp_path):
    storage = tmp_path / "events.json"
    bus = EventBus(storage_file=storage)

    called = []
    bus.subscribe("CLIENT_CREATED", lambda e: called.append(e.id))

    evt = Event(type="CLIENT_CREATED", source="test", entity="client_1", payload={})
    bus.publish(evt)

    assert len(called) == 1
    pending = bus.get_pending_events()
    assert len(pending) == 1
    assert pending[0].id == evt.id

    bus.update_event_status(evt.id, EventStatus.PROCESSED)
    pending_after = bus.get_pending_events()
    assert len(pending_after) == 0
