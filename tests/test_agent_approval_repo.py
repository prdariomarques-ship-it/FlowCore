"""Tests for storage/agent_approval_repo.py -- the persisted
human-in-the-loop approval queue for LEVEL 3+ agent actions.

No pytest-asyncio dependency -- each test wraps its async body in
asyncio.run(), same convention as the rest of this suite.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _repo(tmp_path: Path):
    from storage.agent_approval_repo import AgentApprovalRepository

    return AgentApprovalRepository(db_path=str(tmp_path / "approvals_test.db"))


def _run(coro):
    return asyncio.run(coro)


_PAYLOAD = {"client_id": "c1", "client_name": "Família Teste", "draft": {"subject": "s", "body": "b"}, "channels": ["email"]}


class TestCreateAndGet:
    def test_create_then_get(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            created = await repo.create("office-1", "event-1", "followup_agent", "contact_client", {"kind": "client", "id": "c1"}, _PAYLOAD)
            return created, await repo.get("office-1", created["id"])

        created, fetched = _run(scenario())
        assert fetched == created
        assert fetched["status"] == "pending"
        assert fetched["agent"] == "followup_agent"
        assert fetched["payload"]["client_name"] == "Família Teste"
        assert fetched["result"] is None
        assert fetched["decided_at"] is None

    def test_unknown_approval_is_none(self, tmp_path):
        async def scenario():
            return await _repo(tmp_path).get("office-1", "nope")

        assert _run(scenario()) is None

    def test_scoped_to_one_office(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            created = await repo.create("office-a", "event-1", "followup_agent", "contact_client", {"kind": "client", "id": "c1"}, _PAYLOAD)
            return await repo.get("office-b", created["id"])

        assert _run(scenario()) is None


class TestListApprovals:
    def test_most_recent_first(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            first = await repo.create("office-1", "e1", "a", "contact_client", {"kind": "client", "id": "c1"}, _PAYLOAD)
            second = await repo.create("office-1", "e2", "a", "contact_client", {"kind": "client", "id": "c2"}, _PAYLOAD)
            return first, second, await repo.list_approvals("office-1")

        first, second, items = _run(scenario())
        assert [i["id"] for i in items] == [second["id"], first["id"]]

    def test_filters_by_status(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            pending = await repo.create("office-1", "e1", "a", "contact_client", {"kind": "client", "id": "c1"}, _PAYLOAD)
            approved = await repo.create("office-1", "e2", "a", "contact_client", {"kind": "client", "id": "c2"}, _PAYLOAD)
            await repo.decide("office-1", approved["id"], "approved", "user-1")
            return pending, await repo.list_approvals("office-1", status="pending")

        pending, items = _run(scenario())
        assert [i["id"] for i in items] == [pending["id"]]

    def test_scoped_to_one_office(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            await repo.create("office-a", "e1", "a", "contact_client", {"kind": "client", "id": "c1"}, _PAYLOAD)
            await repo.create("office-b", "e2", "a", "contact_client", {"kind": "client", "id": "c2"}, _PAYLOAD)
            return await repo.list_approvals("office-a")

        items = _run(scenario())
        assert len(items) == 1


class TestUpdatePayload:
    def test_edit_while_pending(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            created = await repo.create("office-1", "e1", "a", "contact_client", {"kind": "client", "id": "c1"}, _PAYLOAD)
            edited = {**_PAYLOAD, "draft": {"subject": "editado", "body": "b"}}
            return await repo.update_payload("office-1", created["id"], edited)

        updated = _run(scenario())
        assert updated["payload"]["draft"]["subject"] == "editado"

    def test_cannot_edit_a_decided_approval(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            created = await repo.create("office-1", "e1", "a", "contact_client", {"kind": "client", "id": "c1"}, _PAYLOAD)
            await repo.decide("office-1", created["id"], "approved", "user-1")
            with pytest.raises(ValueError):
                await repo.update_payload("office-1", created["id"], _PAYLOAD)

        _run(scenario())

    def test_unknown_approval_raises_keyerror(self, tmp_path):
        async def scenario():
            with pytest.raises(KeyError):
                await _repo(tmp_path).update_payload("office-1", "nope", _PAYLOAD)

        _run(scenario())


class TestDecide:
    def test_approve_records_decision(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            created = await repo.create("office-1", "e1", "a", "contact_client", {"kind": "client", "id": "c1"}, _PAYLOAD)
            return await repo.decide("office-1", created["id"], "approved", "user-42", result={"channels": {"email": {"status": "sent"}}})

        decided = _run(scenario())
        assert decided["status"] == "approved"
        assert decided["decided_by_user_id"] == "user-42"
        assert decided["decided_at"] is not None
        assert decided["result"]["channels"]["email"]["status"] == "sent"

    def test_reject_records_decision_without_result(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            created = await repo.create("office-1", "e1", "a", "contact_client", {"kind": "client", "id": "c1"}, _PAYLOAD)
            return await repo.decide("office-1", created["id"], "rejected", "user-42")

        decided = _run(scenario())
        assert decided["status"] == "rejected"
        assert decided["result"] is None

    def test_cannot_decide_twice(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            created = await repo.create("office-1", "e1", "a", "contact_client", {"kind": "client", "id": "c1"}, _PAYLOAD)
            await repo.decide("office-1", created["id"], "approved", "user-1")
            with pytest.raises(ValueError):
                await repo.decide("office-1", created["id"], "rejected", "user-2")

        _run(scenario())

    def test_unknown_approval_raises_keyerror(self, tmp_path):
        async def scenario():
            with pytest.raises(KeyError):
                await _repo(tmp_path).decide("office-1", "nope", "approved", "user-1")

        _run(scenario())

    def test_invalid_status_rejected(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            created = await repo.create("office-1", "e1", "a", "contact_client", {"kind": "client", "id": "c1"}, _PAYLOAD)
            with pytest.raises(ValueError):
                await repo.decide("office-1", created["id"], "pending", "user-1")

        _run(scenario())

    def test_cannot_decide_another_offices_approval(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            created = await repo.create("office-a", "e1", "a", "contact_client", {"kind": "client", "id": "c1"}, _PAYLOAD)
            with pytest.raises(KeyError):
                await repo.decide("office-b", created["id"], "approved", "user-1")

        _run(scenario())
