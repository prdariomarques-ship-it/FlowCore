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

Checked against OWASP's Password Storage and Authentication Cheat
Sheets (cheatsheetseries.owasp.org) — current guidance and two things
fixed as a result:
- 600,000 iterations for PBKDF2-HMAC-SHA256 (OWASP's 2026-current
  number, calibrated to ~0.1s per attempt on consumer hardware) —
  stored self-describing as `pbkdf2_sha256$<iterations>$<salt>$<hash>`
  (the same encoding convention Django's password hasher uses) so a
  *future* iteration bump doesn't invalidate every password already
  hashed at a lower count: verify_password() reads the count baked into
  each stored hash rather than assuming today's constant, and
  transparently re-hashes at the current count on a successful login
  (upgrade-on-login, the standard migration path for this).
- Per-account login throttling (see `login_attempts` below) — OWASP's
  Authentication Cheat Sheet calls out unthrottled login endpoints as
  vulnerable to credential stuffing/brute force.

Four tables:
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
- login_attempts: every login attempt (success or failure), used only to
  throttle brute force per email — see is_rate_limited().
"""
from __future__ import annotations

import hashlib
import secrets
import time
from pathlib import Path
from typing import Any

import aiosqlite

from storage.database import get_db_path

_PBKDF2_ITERATIONS = 600_000  # OWASP Password Storage Cheat Sheet, PBKDF2-HMAC-SHA256
_SESSION_TTL_SECONDS = 14 * 24 * 3600  # 14 days
_MAX_FAILED_ATTEMPTS = 5
_RATE_LIMIT_WINDOW_SECONDS = 15 * 60  # OWASP Authentication Cheat Sheet: throttle, don't leave login unbounded


def _hash_password(password: str, salt: str, iterations: int = _PBKDF2_ITERATIONS) -> str:
    """Self-describing hash: `pbkdf2_sha256$<iterations>$<salt>$<hex digest>`
    — the iteration count travels with the hash so verify_password() can
    check a password against however many iterations it was ORIGINALLY
    hashed with, not today's constant. Without this, raising
    _PBKDF2_ITERATIONS later would silently break every existing
    password (verify would recompute at the new, higher count and never
    match the old hash)."""
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def _verify_password_hash(password: str, salt: str, stored_hash: str) -> bool:
    """Handles both the current `pbkdf2_sha256$<iter>$<salt>$<hex>` format
    and a bare hex digest left over from before this encoding existed
    (verified at the hardcoded legacy count of 200,000 iterations)."""
    if stored_hash.startswith("pbkdf2_sha256$"):
        _, iterations_str, hash_salt, digest = stored_hash.split("$", 3)
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), hash_salt.encode("utf-8"), int(iterations_str)).hex()
        return secrets.compare_digest(candidate, digest)
    legacy_digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000).hex()
    return secrets.compare_digest(legacy_digest, stored_hash)


def _needs_rehash(stored_hash: str) -> bool:
    if not stored_hash.startswith("pbkdf2_sha256$"):
        return True  # legacy bare-hex format
    iterations = int(stored_hash.split("$", 2)[1])
    return iterations < _PBKDF2_ITERATIONS


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
            await db.execute("""
                CREATE TABLE IF NOT EXISTS login_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    attempted_at REAL NOT NULL
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_users_office ON users(office_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_login_attempts_email ON login_attempts(email, attempted_at)")
            await self._ensure_notification_columns(db)
            await db.commit()

    @staticmethod
    async def _ensure_notification_columns(db: aiosqlite.Connection) -> None:
        """telegram_chat_id added after the initial `offices` table shipped
        -- migrate in place (mirrors storage/client_repo.py's
        _ensure_contact_columns). One shared bot token (TELEGRAM_BOT_TOKEN
        env var, runtime/telegram.py) sends to many chats -- each office
        registers its own destination chat_id here so autonomous-agent
        notifications land in that office's own chat, never a single
        shared/global one."""
        cursor = await db.execute("PRAGMA table_info(offices)")
        existing = {row[1] for row in await cursor.fetchall()}
        if "telegram_chat_id" not in existing:
            await db.execute("ALTER TABLE offices ADD COLUMN telegram_chat_id TEXT")

    # ── Offices ─────────────────────────────────────────────────────────────

    async def create_office(self, name: str) -> dict[str, Any]:
        await self.ensure_tables()
        office_id = secrets.token_hex(12)
        now = time.time()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("INSERT INTO offices (id, name, created_at) VALUES (?, ?, ?)", (office_id, name, now))
            await db.commit()
        return {"id": office_id, "name": name, "created_at": now, "telegram_chat_id": None}

    async def count_offices(self) -> int:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM offices")
            row = await cursor.fetchone()
            return row[0]

    async def get_office(self, office_id: str) -> dict[str, Any] | None:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT id, name, created_at, telegram_chat_id FROM offices WHERE id = ?", (office_id,)
            )
            row = await cursor.fetchone()
            return {"id": row[0], "name": row[1], "created_at": row[2], "telegram_chat_id": row[3]} if row else None

    async def list_offices(self) -> list[dict[str, Any]]:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT id, name, created_at, telegram_chat_id FROM offices ORDER BY created_at ASC"
            )
            rows = await cursor.fetchall()
            return [{"id": r[0], "name": r[1], "created_at": r[2], "telegram_chat_id": r[3]} for r in rows]

    async def set_telegram_chat_id(self, office_id: str, chat_id: str | None) -> dict[str, Any] | None:
        """Set (or clear, by passing None/empty) the office's own Telegram
        destination for autonomous-agent notifications. Never inferred --
        an office with none configured simply gets no Telegram alert (see
        agents/orchestrator.py, which checks this before sending)."""
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE offices SET telegram_chat_id = ? WHERE id = ?", (chat_id or None, office_id)
            )
            await db.commit()
        return await self.get_office(office_id)

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
        if not _verify_password_hash(password, salt, password_hash):
            return None
        if _needs_rehash(password_hash):
            # Upgrade-on-login: this account's hash predates the current
            # iteration count (or the pre-fase-0 bare-hex format). Now
            # that the correct password has just been proven, silently
            # re-hash at the current standard — the normal, gradual way
            # to raise KDF cost without a forced mass password reset.
            new_hash = _hash_password(password, salt)
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
                await db.commit()
        return self._public_user(user_id, office_id, stored_email, name, role, created_at)

    # ── Login throttling (OWASP Authentication Cheat Sheet) ─────────────────

    async def record_login_attempt(self, email: str, success: bool) -> None:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO login_attempts (email, success, attempted_at) VALUES (?, ?, ?)",
                (email.lower(), int(success), time.time()),
            )
            await db.commit()

    async def is_rate_limited(self, email: str) -> bool:
        """True when this email has _MAX_FAILED_ATTEMPTS or more failed
        logins within the last _RATE_LIMIT_WINDOW_SECONDS. A single
        success resets the count implicitly — only consecutive-since-
        last-success failures count, so a legitimate user who mistypes
        a few times then gets in isn't punished by attempts from before
        their last successful login."""
        await self.ensure_tables()
        window_start = time.time() - _RATE_LIMIT_WINDOW_SECONDS
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT success FROM login_attempts WHERE email = ? AND attempted_at >= ? ORDER BY attempted_at DESC",
                (email.lower(), window_start),
            )
            rows = await cursor.fetchall()
        failures = 0
        for (success,) in rows:
            if success:
                break
            failures += 1
        return failures >= _MAX_FAILED_ATTEMPTS

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
