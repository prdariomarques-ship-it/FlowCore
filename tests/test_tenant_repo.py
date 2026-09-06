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

    def test_new_office_has_no_telegram_chat_id_by_default(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            return await repo.create_office("Escritório Teste")

        office = asyncio.run(scenario())
        assert office["telegram_chat_id"] is None

    def test_set_and_read_back_telegram_chat_id(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            office = await repo.create_office("Escritório Teste")
            return await repo.set_telegram_chat_id(office["id"], "-100123456")

        updated = asyncio.run(scenario())
        assert updated["telegram_chat_id"] == "-100123456"

    def test_clear_telegram_chat_id(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            office = await repo.create_office("Escritório Teste")
            await repo.set_telegram_chat_id(office["id"], "-100123456")
            return await repo.set_telegram_chat_id(office["id"], None)

        cleared = asyncio.run(scenario())
        assert cleared["telegram_chat_id"] is None

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


class TestPasswordHashingStandard:
    """Checked against OWASP's Password Storage Cheat Sheet
    (cheatsheetseries.owasp.org): PBKDF2-HMAC-SHA256 at 600,000
    iterations, self-describing so a future increase doesn't break
    already-hashed passwords."""

    def test_stored_hash_is_self_describing_and_never_plaintext(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            office = await repo.create_office("Escritório")
            await repo.create_user(office["id"], "dario@example.com", "senha-correta-123", "Dário", "owner")
            import aiosqlite

            async with aiosqlite.connect(repo._db_path) as db:
                cursor = await db.execute("SELECT password_hash FROM users WHERE email = ?", ("dario@example.com",))
                row = await cursor.fetchone()
            return row[0]

        stored = asyncio.run(scenario())
        assert stored.startswith("pbkdf2_sha256$600000$")
        assert "senha-correta-123" not in stored

    def test_legacy_bare_hex_hash_still_verifies(self, tmp_path):
        """A password hashed before this format existed (plain hex
        digest, 200,000 iterations, no `pbkdf2_sha256$...` prefix) must
        keep working — fase 0 shipped before this fix, so real accounts
        could already be in that shape."""
        import hashlib

        from storage.tenant_repo import TenantRepository

        async def scenario():
            repo = _repo(tmp_path)
            office = await repo.create_office("Escritório")
            user = await repo.create_user(office["id"], "dario@example.com", "senha-legada", "Dário", "owner")
            # Overwrite with a pre-fix legacy hash (bare hex, 200k iterations).
            salt = "legacy-salt"
            legacy_hash = hashlib.pbkdf2_hmac("sha256", "senha-legada".encode(), salt.encode(), 200_000).hex()
            import aiosqlite

            async with aiosqlite.connect(repo._db_path) as db:
                await db.execute(
                    "UPDATE users SET password_hash = ?, password_salt = ? WHERE id = ?",
                    (legacy_hash, salt, user["id"]),
                )
                await db.commit()
            return await repo.verify_password("dario@example.com", "senha-legada")

        assert asyncio.run(scenario()) is not None

    def test_successful_login_upgrades_a_legacy_hash_in_place(self, tmp_path):
        import hashlib

        async def scenario():
            repo = _repo(tmp_path)
            office = await repo.create_office("Escritório")
            user = await repo.create_user(office["id"], "dario@example.com", "senha-legada", "Dário", "owner")
            salt = "legacy-salt"
            legacy_hash = hashlib.pbkdf2_hmac("sha256", "senha-legada".encode(), salt.encode(), 200_000).hex()
            import aiosqlite

            async with aiosqlite.connect(repo._db_path) as db:
                await db.execute(
                    "UPDATE users SET password_hash = ?, password_salt = ? WHERE id = ?",
                    (legacy_hash, salt, user["id"]),
                )
                await db.commit()

            await repo.verify_password("dario@example.com", "senha-legada")  # triggers upgrade-on-login

            async with aiosqlite.connect(repo._db_path) as db:
                cursor = await db.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],))
                row = await cursor.fetchone()
            return row[0]

        upgraded = asyncio.run(scenario())
        assert upgraded.startswith("pbkdf2_sha256$600000$")


class TestLoginRateLimiting:
    """OWASP's Authentication Cheat Sheet: throttle repeated login
    attempts to blunt credential stuffing / brute force."""

    def test_not_rate_limited_before_threshold(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            office = await repo.create_office("Escritório")
            await repo.create_user(office["id"], "dario@example.com", "senha-correta", "Dário", "owner")
            for _ in range(4):  # one under the 5-failure threshold
                await repo.record_login_attempt("dario@example.com", success=False)
            return await repo.is_rate_limited("dario@example.com")

        assert asyncio.run(scenario()) is False

    def test_rate_limited_after_threshold_failed_attempts(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            for _ in range(5):
                await repo.record_login_attempt("dario@example.com", success=False)
            return await repo.is_rate_limited("dario@example.com")

        assert asyncio.run(scenario()) is True

    def test_a_success_resets_the_failure_count(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            for _ in range(4):
                await repo.record_login_attempt("dario@example.com", success=False)
            await repo.record_login_attempt("dario@example.com", success=True)
            await repo.record_login_attempt("dario@example.com", success=False)  # only 1 failure since the success
            return await repo.is_rate_limited("dario@example.com")

        assert asyncio.run(scenario()) is False

    def test_rate_limiting_is_per_email_not_global(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            for _ in range(5):
                await repo.record_login_attempt("attacker-target@example.com", success=False)
            return await repo.is_rate_limited("someone-else@example.com")

        assert asyncio.run(scenario()) is False
