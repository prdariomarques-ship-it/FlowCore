"""FlowCore Storage — FlowRepository.

Centralises persistence for Flows (named, ordered lists of steps) and
Executions (a single run of a Flow, with real status/timestamps/per-step
results). Mirrors DocumentRepository's shape: async-only, backed by
aiosqlite, same database file via storage.database.get_db_path().

Sprint 14 removed the previous flows/executions implementation — an
in-memory dict stub whose status never transitioned and whose
started_at/finished_at were always None, wired to nothing. This
repository exists so Sprint 15's real Executor has real persistence to
write to.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite

from storage.database import get_db_path


class FlowRepository:
    """Async repository for the `flows` and `executions` tables."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or get_db_path()
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    # ── Schema ──────────────────────────────────────────────────────────────

    async def ensure_tables(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS flows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    steps TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    flow_id INTEGER NOT NULL,
                    flow_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    step_results TEXT,
                    error TEXT,
                    started_at TIMESTAMP,
                    finished_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()

    # ── Flows ────────────────────────────────────────────────────────────────

    async def create_flow(self, name: str, steps: list[dict[str, Any]]) -> int:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "INSERT INTO flows (name, steps) VALUES (?, ?)",
                (name, json.dumps(steps)),
            )
            await db.commit()
            return cursor.lastrowid

    async def list_flows(self) -> list[dict[str, Any]]:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("SELECT id, name, steps, created_at FROM flows ORDER BY created_at DESC, id DESC")
            rows = await cursor.fetchall()
            return [{"id": r[0], "name": r[1], "steps": json.loads(r[2]), "created_at": r[3]} for r in rows]

    async def get_flow(self, flow_id: int) -> dict[str, Any] | None:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT id, name, steps, created_at FROM flows WHERE id = ?",
                (flow_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return {"id": row[0], "name": row[1], "steps": json.loads(row[2]), "created_at": row[3]}

    async def delete_flow(self, flow_id: int) -> bool:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("DELETE FROM flows WHERE id = ?", (flow_id,))
            await db.commit()
            return cursor.rowcount > 0

    # ── Executions ───────────────────────────────────────────────────────────

    async def create_execution(self, flow_id: int, flow_name: str) -> int:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "INSERT INTO executions (flow_id, flow_name, status) VALUES (?, ?, 'pending')",
                (flow_id, flow_name),
            )
            await db.commit()
            return cursor.lastrowid

    async def start_execution(self, execution_id: int) -> None:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE executions SET status = 'running', started_at = CURRENT_TIMESTAMP WHERE id = ?",
                (execution_id,),
            )
            await db.commit()

    async def finish_execution(
        self,
        execution_id: int,
        status: str,
        step_results: list[dict[str, Any]],
        error: str | None = None,
    ) -> None:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """UPDATE executions
                   SET status = ?, step_results = ?, error = ?, finished_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (status, json.dumps(step_results), error, execution_id),
            )
            await db.commit()

    async def list_executions(self, flow_id: int | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            limit_sql = " LIMIT ?" if limit is not None else ""
            if flow_id is not None:
                params: tuple = (flow_id, limit) if limit is not None else (flow_id,)
                cursor = await db.execute(
                    f"""SELECT id, flow_id, flow_name, status, step_results, error, started_at, finished_at,
                              created_at
                       FROM executions WHERE flow_id = ? ORDER BY created_at DESC, id DESC{limit_sql}""",
                    params,
                )
            else:
                params = (limit,) if limit is not None else ()
                cursor = await db.execute(
                    f"""SELECT id, flow_id, flow_name, status, step_results, error, started_at, finished_at,
                              created_at
                       FROM executions ORDER BY created_at DESC, id DESC{limit_sql}""",
                    params,
                )
            rows = await cursor.fetchall()
            return [self._row_to_execution(r) for r in rows]

    async def get_execution(self, execution_id: int) -> dict[str, Any] | None:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """SELECT id, flow_id, flow_name, status, step_results, error, started_at, finished_at,
                          created_at
                   FROM executions WHERE id = ?""",
                (execution_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_execution(row)

    @staticmethod
    def _row_to_execution(row: tuple) -> dict[str, Any]:
        return {
            "id": row[0],
            "flow_id": row[1],
            "flow_name": row[2],
            "status": row[3],
            "step_results": json.loads(row[4]) if row[4] else [],
            "error": row[5],
            "started_at": row[6],
            "finished_at": row[7],
            "created_at": row[8],
        }
