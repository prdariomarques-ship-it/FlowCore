"""FlowCore Storage — TenantRepository (offices, users, sessions).

Fase 0 of the Office Operating System vision: FlowCore was, until now, a
Personal Execution Operating System for one user (see
FLOWCORE_CONSTITUTION.md, ARCHITECTURE.md) — one shared device API token,
one SQLite file, no login. Turning it into a multi-office product means
every wealth-management record (a client, a compliance policy, an
alert) has to belong to exactly one office, and no request should ever
be able to read or write another office's data.

Same shape as storage/portfolio_repo.py: async-only, aiosqlite, lazy
idempotent `ensure_tables()`, same database file via
storage.database.get_db_path(). No new dependency for password hashing
or sessions — PBKDF2-HMAC-SHA256 (stdlib `hashlib`) with a random salt
per user, and an opaque, revocable, DB-backed session token (stdlib
`secrets`) rather than a JWT library FlowCore doesn't currently depend
on. Simplest robust option for the project's actual dependency budget,
not a shortcut: PBKDF2 is a standard, still-recommended KDF, and a
DB-backed token gets free logout/revocation an unsigned JWT wouldn't.

Three tables:
- offices: the tenant boundary. Every other wealth-management table
  (storage/client_repo.py's office_policies/clients, and eventually
  every future domain table) is scoped by office_id.
- users: one login belongs to exactly one office. `role` is a plain
  string (owner/manager/advisor/assistant/compliance/admin) checked by
  api/tenant_auth.py's require_role() — no separate roles table yet
  since the role set is small and fixed; promote to a table if/when the
  product needs custom per-office roles.
- sessions: opaque bearer tokens, one row per active login. Deleting the
  row is the entire logout implementation.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from pathlib import Path
from typing import Any

import aiosqlite

from storage.database import get_db_path

_PBKDF2_ITERATIONS = 200_000
_SESSION_TTL_SECONDS = 14 * 24 * 3600  # 14 days


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ITERATIONS).hex()


class TenantRepository:
    """Async repository for the `offices`, `users`, and `sessions` tables."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or get_db_path()
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    # ── Schema ──────────────────────────────────────────────────────────────

    async def ensure_tables(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS offices (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    office_id TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (office_id) REFERENCES offices(id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_users_office ON users(office_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)")
            await db.commit()

    # ── Offices ─────────────────────────────────────────────────────────────

    async def create_office(self, name: str) -> dict[str, Any]:
        await self.ensure_tables()
        office_id = secrets.token_hex(12)
        now = time.time()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("INSERT INTO offices (id, name, created_at) VALUES (?, ?, ?)", (office_id, name, now))
            await db.commit()
        return {"id": office_id, "name": name, "created_at": now}

    async def count_offices(self) -> int:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM offices")
            row = await cursor.fetchone()
            return row[0]

    async def get_office(self, office_id: str) -> dict[str, Any] | None:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("SELECT id, name, created_at FROM offices WHERE id = ?", (office_id,))
            row = await cursor.fetchone()
            return {"id": row[0], "name": row[1], "created_at": row[2]} if row else None

    async def list_offices(self) -> list[dict[str, Any]]:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("SELECT id, name, created_at FROM offices ORDER BY created_at ASC")
            rows = await cursor.fetchall()
            return [{"id": r[0], "name": r[1], "created_at": r[2]} for r in rows]

    # ── Users ───────────────────────────────────────────────────────────────

    async def create_user(self, office_id: str, email: str, password: str, name: str, role: str) -> dict[str, Any]:
        """Raises ValueError if the email is already registered (across any
        office — email is the global login identifier)."""
        await self.ensure_tables()
        if await self.get_user_by_email(email):
            raise ValueError(f"email already registered: {email}")
        user_id = secrets.token_hex(12)
        salt = secrets.token_hex(16)
        password_hash = _hash_password(password, salt)
        now = time.time()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO users (id, office_id, email, password_hash, password_salt, name, role, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, office_id, email.lower(), password_hash, salt, name, role, now),
            )
            await db.commit()
        return self._public_user(user_id, office_id, email.lower(), name, role, now)

    async def get_user(self, user_id: str) -> dict[str, Any] | None:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT id, office_id, email, name, role, created_at FROM users WHERE id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            return self._public_user(*row) if row else None

    async def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT id, office_id, email, name, role, created_at FROM users WHERE email = ?", (email.lower(),)
            )
            row = await cursor.fetchone()
            return self._public_user(*row) if row else None

    async def verify_password(self, email: str, password: str) -> dict[str, Any] | None:
        """Returns the public user dict on success, None on wrong email/password."""
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT id, office_id, email, password_hash, password_salt, name, role, created_at "
                "FROM users WHERE email = ?",
                (email.lower(),),
            )
            row = await cursor.fetchone()
        if not row:
            return None
        user_id, office_id, stored_email, password_hash, salt, name, role, created_at = row
        if not secrets.compare_digest(_hash_password(password, salt), password_hash):
            return None
        return self._public_user(user_id, office_id, stored_email, name, role, created_at)

    async def list_users(self, office_id: str) -> list[dict[str, Any]]:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT id, office_id, email, name, role, created_at FROM users WHERE office_id = ? ORDER BY created_at ASC",
                (office_id,),
            )
            rows = await cursor.fetchall()
            return [self._public_user(*r) for r in rows]

    @staticmethod
    def _public_user(user_id: str, office_id: str, email: str, name: str, role: str, created_at: float) -> dict[str, Any]:
        """Never includes password_hash/password_salt — this is the shape
        returned to callers and eventually serialized into API responses."""
        return {"id": user_id, "office_id": office_id, "email": email, "name": name, "role": role, "created_at": created_at}

    # ── Sessions ────────────────────────────────────────────────────────────

    async def create_session(self, user_id: str, ttl_seconds: int = _SESSION_TTL_SECONDS) -> dict[str, Any]:
        await self.ensure_tables()
        token = secrets.token_urlsafe(32)
        now = time.time()
        expires_at = now + ttl_seconds
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token, user_id, now, expires_at),
            )
            await db.commit()
        return {"token": token, "user_id": user_id, "created_at": now, "expires_at": expires_at}

    async def get_session_user(self, token: str) -> dict[str, Any] | None:
        """Resolves a bearer token straight to the public user dict,
        returning None for a missing, expired, or unknown token. Does not
        auto-delete expired rows here — callers doing high-volume auth
        checks shouldn't pay a write on every read; a periodic sweep can
        clean up expired sessions separately if the table ever needs it."""
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("SELECT user_id, expires_at FROM sessions WHERE token = ?", (token,))
            row = await cursor.fetchone()
        if not row:
            return None
        user_id, expires_at = row
        if expires_at < time.time():
            return None
        return await self.get_user(user_id)

    async def delete_session(self, token: str) -> bool:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("DELETE FROM sessions WHERE token = ?", (token,))
            await db.commit()
            return cursor.rowcount > 0
