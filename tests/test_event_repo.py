"""Tests for storage.event_repo.EventRepository (Sprint 19).

Core tier — aiosqlite is a core dependency, no optional-dependency guard
needed (unlike tests touching runtime.observers, which need yfinance).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _make_event(**overrides) -> dict:
    event = {
        "id": "evt-1",
        "timestamp": "2026-08-05T20:00:00+00:00",
        "source": "vix",
        "category": "volatility",
        "symbol": "^VIX",
        "event": "initial_observation",
        "severity": "info",
        "confidence": 0.95,
        "payload": {"value": 15.8},
        "metadata": {"provider": "yfinance"},
    }
    event.update(overrides)
    return event


class TestEnsureTables:
    def test_idempotent(self, tmp_path):
        from storage import EventRepository

        repo = EventRepository(db_path=str(tmp_path / "events.db"))
        asyncio.run(repo.ensure_tables())
        asyncio.run(repo.ensure_tables())  # must not raise


class TestInsertAndList:
    def test_round_trip(self, tmp_path):
        from storage import EventRepository

        repo = EventRepository(db_path=str(tmp_path / "events.db"))
        asyncio.run(repo.insert_event(_make_event()))
        events = asyncio.run(repo.list_events())
        assert len(events) == 1
        assert events[0]["id"] == "evt-1"
        assert events[0]["payload"] == {"value": 15.8}
        assert events[0]["metadata"] == {"provider": "yfinance"}

    def test_filter_by_source(self, tmp_path):
        from storage import EventRepository

        repo = EventRepository(db_path=str(tmp_path / "events.db"))
        asyncio.run(repo.insert_event(_make_event(id="e1", source="vix")))
        asyncio.run(repo.insert_event(_make_event(id="e2", source="gold")))
        vix_events = asyncio.run(repo.list_events(source="vix"))
        assert [e["id"] for e in vix_events] == ["e1"]

    def test_filter_by_since(self, tmp_path):
        from storage import EventRepository

        repo = EventRepository(db_path=str(tmp_path / "events.db"))
        asyncio.run(repo.insert_event(_make_event(id="old", timestamp="2020-01-01T00:00:00+00:00")))
        asyncio.run(repo.insert_event(_make_event(id="new", timestamp="2026-08-05T20:00:00+00:00")))
        recent = asyncio.run(repo.list_events(since="2025-01-01T00:00:00+00:00"))
        assert [e["id"] for e in recent] == ["new"]

    def test_limit(self, tmp_path):
        from storage import EventRepository

        repo = EventRepository(db_path=str(tmp_path / "events.db"))
        for i in range(5):
            asyncio.run(repo.insert_event(_make_event(id=f"e{i}", timestamp=f"2026-08-0{i + 1}T00:00:00+00:00")))
        limited = asyncio.run(repo.list_events(limit=2))
        assert len(limited) == 2

    def test_ordered_newest_first(self, tmp_path):
        from storage import EventRepository

        repo = EventRepository(db_path=str(tmp_path / "events.db"))
        asyncio.run(repo.insert_event(_make_event(id="e1", timestamp="2026-08-01T00:00:00+00:00")))
        asyncio.run(repo.insert_event(_make_event(id="e2", timestamp="2026-08-03T00:00:00+00:00")))
        asyncio.run(repo.insert_event(_make_event(id="e3", timestamp="2026-08-02T00:00:00+00:00")))
        events = asyncio.run(repo.list_events())
        assert [e["id"] for e in events] == ["e2", "e3", "e1"]

    def test_empty_repo_returns_empty_list(self, tmp_path):
        from storage import EventRepository

        repo = EventRepository(db_path=str(tmp_path / "events.db"))
        assert asyncio.run(repo.list_events()) == []

    def test_survives_reopen(self, tmp_path):
        """Simulates a process restart: a new EventRepository instance
        against the same db_path still sees previously inserted events."""
        from storage import EventRepository

        db_path = str(tmp_path / "events.db")
        repo1 = EventRepository(db_path=db_path)
        asyncio.run(repo1.insert_event(_make_event()))

        repo2 = EventRepository(db_path=db_path)
        events = asyncio.run(repo2.list_events())
        assert len(events) == 1
