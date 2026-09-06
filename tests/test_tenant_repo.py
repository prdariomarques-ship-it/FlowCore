"""Tests for storage/tenant_repo.py — offices/users/sessions (fase 0a of
the multi-office FlowCore architecture).

No pytest-asyncio dependency in this project — each test wraps its async
body in a single asyncio.run() call, same convention as
tests/test_flow_repo.py for storage.flow_repo.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _repo(tmp_path: Path):
    from storage.tenant_repo import TenantRepository

    return TenantRepository(db_path=str(tmp_path / "tenant_test.db"))


class TestOffices:
    def test_create_and_get_office(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            office = await repo.create_office("Escritório Teste")
            fetched = await repo.get_office(office["id"])
            return office, fetched

        office, fetched = asyncio.run(scenario())
        assert office["name"] == "Escritório Teste"
        assert fetched == office

    def test_count_offices(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            before = await repo.count_offices()
            await repo.create_office("A")
            await repo.create_office("B")
            after = await repo.count_offices()
            return before, after

        before, after = asyncio.run(scenario())
        assert before == 0
        assert after == 2


class TestUsers:
    def test_create_user_never_returns_password_fields(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            office = await repo.create_office("Escritório")
            return await repo.create_user(office["id"], "dario@example.com", "senha-forte", "Dário", "owner"), office

        user, office = asyncio.run(scenario())
        assert "password_hash" not in user and "password_salt" not in user
        assert user["email"] == "dario@example.com"
        assert user["office_id"] == office["id"]

    def test_duplicate_email_rejected(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            office = await repo.create_office("Escritório")
            await repo.create_user(office["id"], "dario@example.com", "senha1", "Dário", "owner")
            try:
                await repo.create_user(office["id"], "dario@example.com", "senha2", "Outro", "advisor")
                return False
            except ValueError:
                return True

        assert asyncio.run(scenario()) is True

    def test_verify_password_correct_and_wrong(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            office = await repo.create_office("Escritório")
            await repo.create_user(office["id"], "dario@example.com", "senha-correta", "Dário", "owner")
            correct = await repo.verify_password("dario@example.com", "senha-correta")
            wrong = await repo.verify_password("dario@example.com", "senha-errada")
            missing = await repo.verify_password("nao-existe@example.com", "qualquer")
            return correct, wrong, missing

        correct, wrong, missing = asyncio.run(scenario())
        assert correct is not None
        assert wrong is None
        assert missing is None

    def test_list_users_scoped_to_office(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            office_a = await repo.create_office("A")
            office_b = await repo.create_office("B")
            await repo.create_user(office_a["id"], "a@example.com", "senha", "A", "owner")
            await repo.create_user(office_b["id"], "b@example.com", "senha", "B", "owner")
            return await repo.list_users(office_a["id"])

        users_a = asyncio.run(scenario())
        assert len(users_a) == 1
        assert users_a[0]["email"] == "a@example.com"


class TestSessions:
    def test_create_and_resolve_session(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            office = await repo.create_office("Escritório")
            user = await repo.create_user(office["id"], "dario@example.com", "senha", "Dário", "owner")
            session = await repo.create_session(user["id"])
            return user, await repo.get_session_user(session["token"])

        user, resolved = asyncio.run(scenario())
        assert resolved["id"] == user["id"]

    def test_unknown_token_resolves_to_none(self, tmp_path):
        assert asyncio.run(_repo(tmp_path).get_session_user("does-not-exist")) is None

    def test_expired_session_resolves_to_none(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            office = await repo.create_office("Escritório")
            user = await repo.create_user(office["id"], "dario@example.com", "senha", "Dário", "owner")
            session = await repo.create_session(user["id"], ttl_seconds=-1)  # already expired
            return await repo.get_session_user(session["token"])

        assert asyncio.run(scenario()) is None

    def test_logout_deletes_session(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            office = await repo.create_office("Escritório")
            user = await repo.create_user(office["id"], "dario@example.com", "senha", "Dário", "owner")
            session = await repo.create_session(user["id"])
            deleted_first = await repo.delete_session(session["token"])
            resolved_after = await repo.get_session_user(session["token"])
            deleted_second = await repo.delete_session(session["token"])
            return deleted_first, resolved_after, deleted_second

        deleted_first, resolved_after, deleted_second = asyncio.run(scenario())
        assert deleted_first is True
        assert resolved_after is None
        assert deleted_second is False
