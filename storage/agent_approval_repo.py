"""FlowCore Storage — AgentApprovalRepository.

The persisted human-in-the-loop queue (Agent Runtime architecture, §9):
an agent that wants to take a LEVEL 3+ action (one with financial,
legal, or relationship risk — contacting a real client is the first and,
for now, only example) never executes it directly. It prepares the
action and records it here as "pending" instead; the action only
actually runs once a human calls approve() from the dashboard (or,
later, Telegram) — see agents/orchestrator.py's docstring for why this
line is never crossed autonomously.

Persisted, not an in-memory queue or a browser confirm() dialog: an
advisor closes the tab, comes back the next day, and the pending
approval is still exactly where they left it. Same shape as every other
repository here — async-only, aiosqlite, tenant-scoped by office_id.
"""

from __future__ import annotations

import json
import secrets
import time
from pathlib import Path
from typing import Any

import aiosqlite

from storage.database import get_db_path

_VALID_STATUSES = {"pending", "approved", "rejected", "expired"}


class AgentApprovalRepository:
    """Async repository for the `agent_approvals` table."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or get_db_path()
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    async def ensure_tables(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS agent_approvals (
                    id TEXT PRIMARY KEY,
                    office_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    entity_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT,
                    created_at REAL NOT NULL,
                    decided_at REAL,
                    decided_by_user_id TEXT
                )
            """)
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_approvals_office ON agent_approvals(office_id, created_at)"
            )
            await db.commit()

    async def create(
        self, office_id: str, event_id: str, agent: str, action_type: str,
        entity: dict[str, Any], payload: dict[str, Any],
    ) -> dict[str, Any]:
        await self.ensure_tables()
        approval_id = secrets.token_hex(12)
        now = time.time()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO agent_approvals
                   (id, office_id, event_id, agent, action_type, entity_json, payload_json, status,
                    result_json, created_at, decided_at, decided_by_user_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', NULL, ?, NULL, NULL)""",
                (
                    approval_id, office_id, event_id, agent, action_type,
                    json.dumps(entity, ensure_ascii=False), json.dumps(payload, ensure_ascii=False), now,
                ),
            )
            await db.commit()
        return await self.get(office_id, approval_id)

    async def get(self, office_id: str, approval_id: str) -> dict[str, Any] | None:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM agent_approvals WHERE office_id = ? AND id = ?", (office_id, approval_id),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            columns = [d[0] for d in cursor.description]
            return self._row_to_dict(dict(zip(columns, row)))

    async def list_approvals(self, office_id: str, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        await self.ensure_tables()
        query = "SELECT * FROM agent_approvals WHERE office_id = ?"
        params: list[Any] = [office_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            columns = [d[0] for d in cursor.description]
            return [self._row_to_dict(dict(zip(columns, r))) for r in rows]

    async def update_payload(self, office_id: str, approval_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """The "EDITAR" step -- an advisor can adjust the prepared action
        (e.g. tweak the drafted message) before approving it. Only
        meaningful while still pending; raises ValueError otherwise so a
        stale edit on an already-decided approval fails loudly instead of
        silently rewriting history."""
        existing = await self.get(office_id, approval_id)
        if existing is None:
            raise KeyError(approval_id)
        if existing["status"] != "pending":
            raise ValueError(f"cannot edit a {existing['status']} approval")
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE agent_approvals SET payload_json = ? WHERE office_id = ? AND id = ?",
                (json.dumps(payload, ensure_ascii=False), office_id, approval_id),
            )
            await db.commit()
        return await self.get(office_id, approval_id)

    async def decide(
        self, office_id: str, approval_id: str, status: str, decided_by_user_id: str,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Records a human decision. Raises KeyError if the approval
        doesn't exist (tenant-scoped, same guarantee as every other
        repository here), ValueError if it isn't pending any more --
        approving/rejecting twice is a bug in the caller, never silently
        allowed."""
        if status not in _VALID_STATUSES - {"pending"}:
            raise ValueError(f"invalid decision status: {status!r}")
        existing = await self.get(office_id, approval_id)
        if existing is None:
            raise KeyError(approval_id)
        if existing["status"] != "pending":
            raise ValueError(f"approval {approval_id} is already {existing['status']}")
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE agent_approvals SET status = ?, decided_at = ?, decided_by_user_id = ?, result_json = ? "
                "WHERE office_id = ? AND id = ?",
                (status, time.time(), decided_by_user_id, json.dumps(result, ensure_ascii=False) if result else None, office_id, approval_id),
            )
            await db.commit()
        return await self.get(office_id, approval_id)

    @staticmethod
    def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"], "office_id": row["office_id"], "event_id": row["event_id"],
            "agent": row["agent"], "action_type": row["action_type"],
            "entity": json.loads(row["entity_json"]), "payload": json.loads(row["payload_json"]),
            "status": row["status"], "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "created_at": row["created_at"], "decided_at": row["decided_at"],
            "decided_by_user_id": row["decided_by_user_id"],
        }
