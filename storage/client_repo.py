"""FlowCore Storage — ClientRepository (office_policies + clients).

Fase 0c of the multi-office architecture. Replaces the old single-
install file-based storage this Wealth Copilot work started with
(runtime/portfolio/reference.py's ~/.flowcore/portfolio_moderate_1m.json
and runtime/portfolio/demo_clients.py's ~/.flowcore/demo_clients.json) —
those made sense for one user on one device, but a second office signing
up would have silently shared (or clobbered) the first office's policy
and positions through the same file. Every row here is scoped by
office_id instead.

Same shape as storage/portfolio_repo.py and storage/tenant_repo.py:
async-only, aiosqlite, lazy idempotent `ensure_tables()`.

Two tables:
- office_policies: one row per office — the real investment policy
  (target_allocation/sleeve_limits/review_policy) ComplianceAgent
  evaluates against, plus the policy's own tracked position
  (current_allocation) exactly like the old bundled
  portfolio_moderate_1m.json did double duty as both "the model" and "a
  position to check." Seeded from that same bundled JSON at office
  creation (see seed_office()), then editable per office.
- clients: real position-holders evaluated against their office's
  policy. Seeded with the 27 example clients (config/demo_clients.json)
  ONLY for the one bootstrap "FlowCore Demo" office — every office
  created afterward via real signup starts with zero clients (honest
  empty state, no fabricated clients for a paying customer's account).
  `original_allocation_json` is set only for seeded demo clients, so
  reset_demo_clients() has something real to revert to; a client with no
  known original state can't be "reset" (nothing invented to fall back on).
"""

from __future__ import annotations

import json
import secrets
import time
from pathlib import Path
from typing import Any

import aiosqlite

from storage.database import get_db_path

_BUNDLED_POLICY = Path(__file__).resolve().parents[1] / "config" / "portfolio_moderate_1m.json"
_BUNDLED_DEMO_CLIENTS = Path(__file__).resolve().parents[1] / "config" / "demo_clients.json"

_POLICY_FALLBACK: dict[str, Any] = {
    "id": "moderate-ia-1m",
    "name": "Carteira Moderada — R$ 1 milhão",
    "reference_value": 1000000,
    "profile": "",
    "target_allocation": [],
    "sleeve_limits": {},
    "review_policy": {},
    "current_allocation": {},
}


def _load_bundled_policy() -> dict[str, Any]:
    try:
        return json.loads(_BUNDLED_POLICY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(_POLICY_FALLBACK)


def _load_bundled_demo_clients() -> list[dict[str, Any]]:
    try:
        data = json.loads(_BUNDLED_DEMO_CLIENTS.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


class ClientRepository:
    """Async repository for the `office_policies` and `clients` tables."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or get_db_path()
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    # ── Schema ──────────────────────────────────────────────────────────────

    async def ensure_tables(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS office_policies (
                    office_id TEXT PRIMARY KEY,
                    policy_json TEXT NOT NULL,
                    customized INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS clients (
                    id TEXT NOT NULL,
                    office_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    profile TEXT NOT NULL DEFAULT '',
                    reference_value REAL,
                    current_allocation_json TEXT NOT NULL DEFAULT '{}',
                    original_allocation_json TEXT,
                    is_demo INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (office_id, id)
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_clients_office ON clients(office_id)")
            await self._ensure_contact_columns(db)
            await self._ensure_investor_classification_columns(db)
            await db.commit()

    @staticmethod
    async def _ensure_contact_columns(db: aiosqlite.Connection) -> None:
        """email/phone added after the initial `clients` table shipped —
        `CREATE TABLE IF NOT EXISTS` above doesn't add columns to an
        already-existing table, so migrate in place. Real contact fields,
        always nullable: never fabricated for a client (the 27 example
        clients are fictitious people, so they get none at all — see
        seed_office() — and a real client only has one once someone
        actually enters it)."""
        cursor = await db.execute("PRAGMA table_info(clients)")
        existing = {row[1] for row in await cursor.fetchall()}
        if "email" not in existing:
            await db.execute("ALTER TABLE clients ADD COLUMN email TEXT")
        if "phone" not in existing:
            await db.execute("ALTER TABLE clients ADD COLUMN phone TEXT")

    @staticmethod
    async def _ensure_investor_classification_columns(db: aiosqlite.Connection) -> None:
        """CVM Resolução 30/2021 investor category (see config/
        investor_classification.py), added after the initial `clients`
        table shipped — same in-place migration as _ensure_contact_columns.
        investor_category defaults to 'geral' (every existing client is
        honestly unclassified until an advisor records a real declaration
        via set_investor_classification); the other three columns stay
        NULL until then — never inferred or backfilled."""
        cursor = await db.execute("PRAGMA table_info(clients)")
        existing = {row[1] for row in await cursor.fetchall()}
        if "investor_category" not in existing:
            await db.execute("ALTER TABLE clients ADD COLUMN investor_category TEXT NOT NULL DEFAULT 'geral'")
        if "investor_declared_investments" not in existing:
            await db.execute("ALTER TABLE clients ADD COLUMN investor_declared_investments REAL")
        if "investor_certification" not in existing:
            await db.execute("ALTER TABLE clients ADD COLUMN investor_certification TEXT")
        if "investor_attestation_at" not in existing:
            await db.execute("ALTER TABLE clients ADD COLUMN investor_attestation_at REAL")

    # ── Seeding (called once, at office creation) ───────────────────────────

    async def seed_office(self, office_id: str, with_demo_clients: bool) -> None:
        await self.ensure_tables()
        now = time.time()
        policy = _load_bundled_policy()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO office_policies (office_id, policy_json, customized, updated_at) "
                "VALUES (?, ?, 0, ?)",
                (office_id, json.dumps(policy, ensure_ascii=False), now),
            )
            if with_demo_clients:
                for c in _load_bundled_demo_clients():
                    allocation = json.dumps(c.get("current_allocation") or {}, ensure_ascii=False)
                    # email/phone deliberately NULL — these 27 are fictitious
                    # people (see runtime/portfolio/demo_clients.py); inventing
                    # contact details for them would fabricate PII-shaped data
                    # for a person who doesn't exist, worse than the financial
                    # placeholder numbers, so real outreach can never target them.
                    await db.execute(
                        """INSERT OR REPLACE INTO clients
                           (id, office_id, name, profile, reference_value, current_allocation_json,
                            original_allocation_json, is_demo, created_at, updated_at, email, phone)
                           VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, NULL, NULL)""",
                        (
                            c["id"],
                            office_id,
                            c.get("name", ""),
                            c.get("profile", ""),
                            c.get("reference_value"),
                            allocation,
                            allocation,
                            now,
                            now,
                        ),
                    )
            await db.commit()

    # ── Office policy ────────────────────────────────────────────────────────

    async def get_office_policy(self, office_id: str) -> dict[str, Any]:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("SELECT policy_json FROM office_policies WHERE office_id = ?", (office_id,))
            row = await cursor.fetchone()
        if row is None:
            # Defensive fallback for an office that was never seeded (should
            # not normally happen — seed_office() runs at office creation).
            return dict(_POLICY_FALLBACK)
        return json.loads(row[0])

    async def is_policy_customized(self, office_id: str) -> bool:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("SELECT customized FROM office_policies WHERE office_id = ?", (office_id,))
            row = await cursor.fetchone()
            return bool(row and row[0])

    async def save_office_policy(self, office_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        current = await self.get_office_policy(office_id)
        current.update({k: v for k, v in updates.items() if v is not None})
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO office_policies (office_id, policy_json, customized, updated_at) "
                "VALUES (?, ?, 1, ?)",
                (office_id, json.dumps(current, ensure_ascii=False), time.time()),
            )
            await db.commit()
        return current

    async def reset_office_policy(self, office_id: str) -> dict[str, Any]:
        policy = _load_bundled_policy()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO office_policies (office_id, policy_json, customized, updated_at) "
                "VALUES (?, ?, 0, ?)",
                (office_id, json.dumps(policy, ensure_ascii=False), time.time()),
            )
            await db.commit()
        return policy

    # ── Clients ─────────────────────────────────────────────────────────────

    _CLIENT_COLUMNS = (
        "id, office_id, name, profile, reference_value, current_allocation_json, is_demo, "
        "created_at, updated_at, email, phone, investor_category, investor_declared_investments, "
        "investor_certification, investor_attestation_at"
    )

    async def list_clients(self, office_id: str) -> list[dict[str, Any]]:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                f"SELECT {self._CLIENT_COLUMNS} FROM clients WHERE office_id = ? ORDER BY created_at ASC",
                (office_id,),
            )
            rows = await cursor.fetchall()
            return [self._row_to_client(r) for r in rows]

    async def get_client(self, office_id: str, client_id: str) -> dict[str, Any] | None:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                f"SELECT {self._CLIENT_COLUMNS} FROM clients WHERE office_id = ? AND id = ?",
                (office_id, client_id),
            )
            row = await cursor.fetchone()
            return self._row_to_client(row) if row else None

    async def create_client(
        self,
        office_id: str,
        name: str,
        profile: str = "",
        reference_value: float | None = None,
        current_allocation: dict[str, float] | None = None,
        email: str | None = None,
        phone: str | None = None,
    ) -> dict[str, Any]:
        """A real, advisor-entered client -- is_demo=0 and
        original_allocation_json=NULL (there is no fabricated "original"
        state to revert to, unlike the 27 seeded example clients: see
        reset_demo_clients()'s own docstring for why that's a no-op for
        a client with no known original position)."""
        await self.ensure_tables()
        client_id = f"client-{secrets.token_hex(8)}"
        now = time.time()
        allocation = json.dumps(current_allocation or {}, ensure_ascii=False)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO clients
                   (id, office_id, name, profile, reference_value, current_allocation_json,
                    original_allocation_json, is_demo, created_at, updated_at, email, phone)
                   VALUES (?, ?, ?, ?, ?, ?, NULL, 0, ?, ?, ?, ?)""",
                (client_id, office_id, name, profile, reference_value, allocation, now, now, email, phone),
            )
            await db.commit()
        return await self.get_client(office_id, client_id)

    async def save_client_allocation(
        self, office_id: str, client_id: str, current_allocation: dict[str, float]
    ) -> dict[str, Any]:
        """Merge `current_allocation` onto one client's position. Scoped by
        office_id in the WHERE clause of every query — a client id alone
        (even if guessed correctly) can never be edited from the wrong
        office's session. Raises KeyError if no such client in this office."""
        existing = await self.get_client(office_id, client_id)
        if existing is None:
            raise KeyError(client_id)
        merged = {**existing["current_allocation"], **current_allocation}
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE clients SET current_allocation_json = ?, updated_at = ? WHERE office_id = ? AND id = ?",
                (json.dumps(merged, ensure_ascii=False), time.time(), office_id, client_id),
            )
            await db.commit()
        return await self.get_client(office_id, client_id)

    async def save_client_contact(
        self, office_id: str, client_id: str, email: str | None, phone: str | None
    ) -> dict[str, Any]:
        """Set (or clear, by passing an empty string) a real client's own
        contact info — never inferred, never defaulted. Raises KeyError if
        no such client in this office (same tenant-scoping guarantee as
        save_client_allocation)."""
        existing = await self.get_client(office_id, client_id)
        if existing is None:
            raise KeyError(client_id)
        new_email = existing["email"] if email is None else (email or None)
        new_phone = existing["phone"] if phone is None else (phone or None)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE clients SET email = ?, phone = ?, updated_at = ? WHERE office_id = ? AND id = ?",
                (new_email, new_phone, time.time(), office_id, client_id),
            )
            await db.commit()
        return await self.get_client(office_id, client_id)

    async def set_investor_classification(
        self,
        office_id: str,
        client_id: str,
        declared_investments: float | None,
        certification: str | None,
    ) -> dict[str, Any]:
        """Records a client's investor category per CVM Resolução 30/2021
        (config/investor_classification.py) — the category is always
        *derived* from declared_investments/certification, never accepted
        directly, so a caller can't simply assert "profissional" without
        the numbers/certification behind it. Stamps investor_attestation_at
        with the moment this was recorded whenever the result isn't
        'geral', standing in for the written self-declaration (termo,
        Anexos A/B) the resolution requires; passing both None resets a
        client back to 'geral' (e.g. reverting an earlier declaration) and
        clears the attestation timestamp. Raises KeyError if no such
        client in this office (same tenant-scoping guarantee as
        save_client_allocation)."""
        from config.investor_classification import suggest_investor_category

        existing = await self.get_client(office_id, client_id)
        if existing is None:
            raise KeyError(client_id)
        category = suggest_investor_category(declared_investments, certification)
        attested_at = time.time() if category != "geral" else None
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """UPDATE clients SET investor_category = ?, investor_declared_investments = ?,
                   investor_certification = ?, investor_attestation_at = ?, updated_at = ?
                   WHERE office_id = ? AND id = ?""",
                (category, declared_investments, certification, attested_at, time.time(), office_id, client_id),
            )
            await db.commit()
        return await self.get_client(office_id, client_id)

    async def reset_demo_clients(self, office_id: str) -> list[dict[str, Any]]:
        """Reverts every demo client in this office to its original seeded
        position. A no-op for clients with no known original state (never
        fabricates one)."""
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """UPDATE clients SET current_allocation_json = original_allocation_json, updated_at = ?
                   WHERE office_id = ? AND is_demo = 1 AND original_allocation_json IS NOT NULL""",
                (time.time(), office_id),
            )
            await db.commit()
        return await self.list_clients(office_id)

    @staticmethod
    def _row_to_client(row: tuple) -> dict[str, Any]:
        return {
            "id": row[0],
            "office_id": row[1],
            "name": row[2],
            "profile": row[3],
            "reference_value": row[4],
            "current_allocation": json.loads(row[5]),
            "is_demo": bool(row[6]),
            "created_at": row[7],
            "updated_at": row[8],
            "email": row[9],
            "phone": row[10],
            "investor_category": row[11],
            "investor_declared_investments": row[12],
            "investor_certification": row[13],
            "investor_attestation_at": row[14],
        }
