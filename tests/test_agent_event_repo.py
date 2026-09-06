"""Tests for storage/agent_event_repo.py -- the generic, extensible
event bus the autonomous Agent Runtime is built on (distinct from
storage/event_repo.py's market-data-only EventRepository).

No pytest-asyncio dependency in this project -- each test wraps its
async body in asyncio.run(), same convention as tests/test_client_repo.py.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.events import AgentEvent  # noqa: E402


def _repo(tmp_path: Path):
    from storage.agent_event_repo import AgentEventRepository

    return AgentEventRepository(db_path=str(tmp_path / "events_test.db"))


def _event(**overrides) -> AgentEvent:
    defaults = dict(
        type="PORTFOLIO_OUT_OF_PROFILE", source="compliance_agent",
        entity={"kind": "client", "id": "demo-client-21"},
        payload={"message": "Renda Fixa 2.0 p.p. acima do limite"}, priority="HIGH",
    )
    defaults.update(overrides)
    return AgentEvent(**defaults)


class TestPublishAndGet:
    def test_publish_then_get(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            published = await repo.publish("office-1", _event())
            return published, await repo.get_event("office-1", published["id"])

        published, fetched = asyncio.run(scenario())
        assert fetched == published
        assert fetched["type"] == "PORTFOLIO_OUT_OF_PROFILE"
        assert fetched["entity"] == {"kind": "client", "id": "demo-client-21"}
        assert fetched["status"] == "pending"
        assert fetched["decision"] is None

    def test_unknown_event_is_none_not_an_error(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            return await repo.get_event("office-1", "nope")

        assert asyncio.run(scenario()) is None

    def test_event_from_another_office_is_invisible(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            published = await repo.publish("office-a", _event())
            return await repo.get_event("office-b", published["id"])

        assert asyncio.run(scenario()) is None


class TestListEvents:
    def test_lists_most_recent_first(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            first = await repo.publish("office-1", _event(entity={"kind": "client", "id": "c1"}))
            second = await repo.publish("office-1", _event(entity={"kind": "client", "id": "c2"}))
            return first, second, await repo.list_events("office-1")

        first, second, items = asyncio.run(scenario())
        assert [i["id"] for i in items] == [second["id"], first["id"]]

    def test_filters_by_status(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            pending = await repo.publish("office-1", _event(entity={"kind": "client", "id": "c1"}))
            processed = await repo.publish("office-1", _event(entity={"kind": "client", "id": "c2"}))
            await repo.record_decision("office-1", processed["id"], "processed", {"action": "notify"})
            return pending, await repo.list_events("office-1", status="pending")

        pending, items = asyncio.run(scenario())
        assert [i["id"] for i in items] == [pending["id"]]

    def test_scoped_to_one_office(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            await repo.publish("office-a", _event())
            await repo.publish("office-b", _event())
            return await repo.list_events("office-a")

        items = asyncio.run(scenario())
        assert len(items) == 1


class TestDedup:
    def test_no_duplicate_before_anything_published(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            return await repo.has_recent_duplicate("office-1", _event().dedup_key())

        assert asyncio.run(scenario()) is False

    def test_same_situation_is_a_duplicate(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            event = _event()
            await repo.publish("office-1", event)
            return await repo.has_recent_duplicate("office-1", event.dedup_key())

        assert asyncio.run(scenario()) is True

    def test_different_entity_is_not_a_duplicate(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            await repo.publish("office-1", _event(entity={"kind": "client", "id": "c1"}))
            different = _event(entity={"kind": "client", "id": "c2"})
            return await repo.has_recent_duplicate("office-1", different.dedup_key())

        assert asyncio.run(scenario()) is False

    def test_different_office_is_not_a_duplicate(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            event = _event()
            await repo.publish("office-a", event)
            return await repo.has_recent_duplicate("office-b", event.dedup_key())

        assert asyncio.run(scenario()) is False

    def test_outside_the_window_is_not_a_duplicate(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            event = _event()
            await repo.publish("office-1", event)
            return await repo.has_recent_duplicate("office-1", event.dedup_key(), window_seconds=-1)

        assert asyncio.run(scenario()) is False


class TestRecordDecision:
    def test_updates_status_and_stores_decision(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            published = await repo.publish("office-1", _event())
            return await repo.record_decision(
                "office-1", published["id"], "processed",
                {"agent": "client_intelligence", "action": "notify_advisor", "reasoning_source": "template_fallback"},
            )

        updated = asyncio.run(scenario())
        assert updated["status"] == "processed"
        assert updated["decision"]["action"] == "notify_advisor"

    def test_cannot_record_decision_for_another_offices_event(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            published = await repo.publish("office-a", _event())
            await repo.record_decision("office-b", published["id"], "processed", {"action": "x"})
            return await repo.get_event("office-a", published["id"])

        untouched = asyncio.run(scenario())
        assert untouched["status"] == "pending"
        assert untouched["decision"] is None
