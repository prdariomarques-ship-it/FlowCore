"""FlowCore Storage — AgentEventRepository.

Persists agents.events.AgentEvent for the autonomous Agent Runtime.
Distinct from storage/event_repo.py's EventRepository, which is a
market-data-specific table (Sprint 18 observers -> Macro Score Engine) —
this one is the generic, extensible event bus described in the "System
of Execution" architecture: CLIENT_*, PORTFOLIO_*, TASK_*, etc.

Same shape as every other repository in this codebase: async-only,
aiosqlite, lazy idempotent ensure_tables(), tenant-scoped by office_id in
every query -- one office's events are never visible through another
office's session, same guarantee storage/client_repo.py already gives
clients and policies.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import aiosqlite

from storage.database import get_db_path

_DEDUP_WINDOW_SECONDS = 24 * 3600


class AgentEventRepository:
    """Async repository for the `agent_events` table."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or get_db_path()
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    async def ensure_tables(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS agent_events (
                    id TEXT PRIMARY KEY,
                    office_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    entity_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    dedup_key TEXT NOT NULL,
                    decision_json TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_events_office ON agent_events(office_id, created_at)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_events_dedup ON agent_events(office_id, dedup_key, created_at)"
            )
            await db.commit()

    # ── Publish / lookup ─────────────────────────────────────────────────────

    async def publish(self, office_id: str, event: "Any") -> dict[str, Any]:
        """Persists `event` (an agents.events.AgentEvent) for this office.
        Caller is responsible for dedup (see has_recent_duplicate) --
        this method always inserts."""
        await self.ensure_tables()
        now = time.time()
        row = event.to_dict()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO agent_events
                   (id, office_id, type, source, entity_json, payload_json, priority, status,
                    metadata_json, dedup_key, decision_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
                (
                    row["id"],
                    office_id,
                    row["type"],
                    row["source"],
                    json.dumps(row["entity"], ensure_ascii=False),
                    json.dumps(row["payload"], ensure_ascii=False),
                    row["priority"],
                    row["status"],
                    json.dumps(row["metadata"], ensure_ascii=False),
                    event.dedup_key(),
                    now,
                    now,
                ),
            )
            await db.commit()
        return await self.get_event(office_id, row["id"])

    async def has_recent_duplicate(
        self, office_id: str, dedup_key: str, window_seconds: float = _DEDUP_WINDOW_SECONDS
    ) -> bool:
        """True if this office already has an event with the same
        dedup_key (same type+entity+payload -- "the same situation")
        published within the window. Keeps an ongoing, unchanged
        violation from being re-published (and re-notified) every single
        observation cycle."""
        await self.ensure_tables()
        cutoff = time.time() - window_seconds
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM agent_events WHERE office_id = ? AND dedup_key = ? AND created_at >= ? LIMIT 1",
                (office_id, dedup_key, cutoff),
            )
            return (await cursor.fetchone()) is not None

    async def get_event(self, office_id: str, event_id: str) -> dict[str, Any] | None:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM agent_events WHERE office_id = ? AND id = ?",
                (office_id, event_id),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            columns = [d[0] for d in cursor.description]
            return self._row_to_dict(dict(zip(columns, row)))

    async def list_events(
        self,
        office_id: str,
        status: str | None = None,
        type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        await self.ensure_tables()
        query = "SELECT * FROM agent_events WHERE office_id = ?"
        params: list[Any] = [office_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        if type:
            query += " AND type = ?"
            params.append(type)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            columns = [d[0] for d in cursor.description]
            return [self._row_to_dict(dict(zip(columns, r))) for r in rows]

    async def count_by_status(self, office_id: str) -> dict[str, int]:
        """Exact counts per status for this office -- used by the Agent
        Runtime observability dashboard (§18), not derived from a
        possibly-truncated list_events() page."""
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT status, COUNT(*) FROM agent_events WHERE office_id = ? GROUP BY status",
                (office_id,),
            )
            rows = await cursor.fetchall()
            return {r[0]: r[1] for r in rows}

    async def count_by_type(self, office_id: str) -> dict[str, int]:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT type, COUNT(*) FROM agent_events WHERE office_id = ? GROUP BY type",
                (office_id,),
            )
            rows = await cursor.fetchall()
            return {r[0]: r[1] for r in rows}

    async def first_seen(self, office_id: str, dedup_key: str) -> float | None:
        """The created_at of the earliest event with this dedup_key still
        on record -- "how long has this exact situation been open", used
        by agents/observer_loop.py to decide when an unaddressed
        violation crosses the bar into CLIENT_FOLLOWUP_OVERDUE."""
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT MIN(created_at) FROM agent_events WHERE office_id = ? AND dedup_key = ?",
                (office_id, dedup_key),
            )
            row = await cursor.fetchone()
            return row[0] if row and row[0] is not None else None

    async def mark_resolved(self, office_id: str, event_id: str) -> dict[str, Any] | None:
        """A previously-processed event whose underlying situation no
        longer exists (e.g. the client's portfolio is back in profile) --
        distinct from "processed", so agents/observer_loop.py can tell
        "handled and done" apart from "handled and still open"."""
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE agent_events SET status = 'resolved', updated_at = ? WHERE office_id = ? AND id = ?",
                (time.time(), office_id, event_id),
            )
            await db.commit()
        return await self.get_event(office_id, event_id)

    async def record_decision(
        self, office_id: str, event_id: str, status: str, decision: dict[str, Any]
    ) -> dict[str, Any] | None:
        """CoreOrchestrator calls this once it has finished handling an
        event -- persists the outcome (reasoning, action taken, whether a
        notification was actually sent) and moves status out of
        "pending"/"processing"."""
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE agent_events SET status = ?, decision_json = ?, updated_at = ? WHERE office_id = ? AND id = ?",
                (status, json.dumps(decision, ensure_ascii=False), time.time(), office_id, event_id),
            )
            await db.commit()
        return await self.get_event(office_id, event_id)

    @staticmethod
    def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "office_id": row["office_id"],
            "type": row["type"],
            "source": row["source"],
            "entity": json.loads(row["entity_json"]),
            "payload": json.loads(row["payload_json"]),
            "priority": row["priority"],
            "status": row["status"],
            "metadata": json.loads(row["metadata_json"]),
            "dedup_key": row["dedup_key"],
            "decision": json.loads(row["decision_json"]) if row["decision_json"] else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
