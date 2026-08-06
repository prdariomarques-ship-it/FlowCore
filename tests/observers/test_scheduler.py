"""Tests for runtime.observers.scheduler.ObserverScheduler."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

yfinance = pytest.importorskip("yfinance")

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _make_registry_with(*observers):
    from runtime.observers.registry import ObserverRegistry

    reg = ObserverRegistry()
    for o in observers:
        reg.register(o)
    return reg


class _FixedObserver:
    def __init__(self, source, events):
        self.source = source
        self.category = "test"
        self._events = events

    def observe(self):
        return self._events


class _FailingObserver:
    def __init__(self, source):
        self.source = source
        self.category = "test"

    def observe(self):
        from runtime.observers.base import ObserverError

        raise ObserverError("simulated failure")


class TestRunOnce:
    def test_aggregates_events_from_all_observers(self):
        from runtime.observers.event import new_event
        from runtime.observers.scheduler import ObserverScheduler

        e1 = new_event(source="a", category="test", symbol="A", event="x", payload={})
        e2 = new_event(source="b", category="test", symbol="B", event="x", payload={})
        reg = _make_registry_with(_FixedObserver("a", [e1]), _FixedObserver("b", [e2]))
        scheduler = ObserverScheduler(reg)

        events = asyncio.run(scheduler.run_once())
        assert {e.source for e in events} == {"a", "b"}

    def test_one_failing_observer_does_not_fail_the_batch(self):
        from runtime.observers.event import new_event
        from runtime.observers.scheduler import ObserverScheduler

        e1 = new_event(source="a", category="test", symbol="A", event="x", payload={})
        reg = _make_registry_with(_FixedObserver("a", [e1]), _FailingObserver("b"))
        scheduler = ObserverScheduler(reg)

        events = asyncio.run(scheduler.run_once())
        assert [e.source for e in events] == ["a"]

    def test_empty_registry_returns_empty_list(self):
        from runtime.observers.scheduler import ObserverScheduler

        scheduler = ObserverScheduler(_make_registry_with())
        assert asyncio.run(scheduler.run_once()) == []


class TestRunSource:
    def test_returns_and_persists_events(self, tmp_path):
        from storage import EventRepository

        from runtime.observers.event import new_event
        from runtime.observers.scheduler import ObserverScheduler

        e1 = new_event(source="a", category="test", symbol="A", event="x", payload={})
        reg = _make_registry_with(_FixedObserver("a", [e1]))
        repo = EventRepository(db_path=str(tmp_path / "events.db"))
        scheduler = ObserverScheduler(reg, event_repo=repo)

        events = asyncio.run(scheduler.run_source("a"))
        assert [e.source for e in events] == ["a"]
        persisted = asyncio.run(repo.list_events())
        assert len(persisted) == 1
        assert persisted[0]["id"] == e1.id

    def test_unknown_source_raises(self):
        from runtime.observers.base import ObserverError
        from runtime.observers.scheduler import ObserverScheduler

        scheduler = ObserverScheduler(_make_registry_with())
        with pytest.raises(ObserverError):
            asyncio.run(scheduler.run_source("bogus"))


class TestPersistence:
    def test_run_once_persists_all_events(self, tmp_path):
        from storage import EventRepository

        from runtime.observers.event import new_event
        from runtime.observers.scheduler import ObserverScheduler

        e1 = new_event(source="a", category="test", symbol="A", event="x", payload={})
        e2 = new_event(source="b", category="test", symbol="B", event="x", payload={})
        reg = _make_registry_with(_FixedObserver("a", [e1]), _FixedObserver("b", [e2]))
        repo = EventRepository(db_path=str(tmp_path / "events.db"))
        scheduler = ObserverScheduler(reg, event_repo=repo)

        asyncio.run(scheduler.run_once())
        persisted = asyncio.run(repo.list_events())
        assert {e["source"] for e in persisted} == {"a", "b"}

    def test_no_event_repo_means_no_persistence_attempt(self):
        # Backward compatible: omitting event_repo (the default) must not
        # touch storage at all — covered implicitly by every test above
        # that constructs ObserverScheduler(reg) with no second arg, but
        # asserted explicitly here too.
        from runtime.observers.event import new_event
        from runtime.observers.scheduler import ObserverScheduler

        e1 = new_event(source="a", category="test", symbol="A", event="x", payload={})
        reg = _make_registry_with(_FixedObserver("a", [e1]))
        scheduler = ObserverScheduler(reg)
        assert scheduler._event_repo is None
        events = asyncio.run(scheduler.run_once())
        assert len(events) == 1

    def test_persistence_failure_does_not_break_run_once(self, tmp_path):
        from unittest.mock import AsyncMock

        from runtime.observers.event import new_event
        from runtime.observers.scheduler import ObserverScheduler

        e1 = new_event(source="a", category="test", symbol="A", event="x", payload={})
        reg = _make_registry_with(_FixedObserver("a", [e1]))
        broken_repo = AsyncMock()
        broken_repo.insert_event.side_effect = RuntimeError("disk full")
        scheduler = ObserverScheduler(reg, event_repo=broken_repo)

        events = asyncio.run(scheduler.run_once())
        assert [e.source for e in events] == ["a"]


class TestRunForever:
    def test_runs_multiple_cycles_until_cancelled(self):
        from runtime.observers.event import new_event
        from runtime.observers.scheduler import ObserverScheduler

        e1 = new_event(source="a", category="test", symbol="A", event="x", payload={})
        reg = _make_registry_with(_FixedObserver("a", [e1]))
        scheduler = ObserverScheduler(reg)

        async def run_and_cancel():
            task = asyncio.create_task(scheduler.run_forever(interval_seconds=0))
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(run_and_cancel())
