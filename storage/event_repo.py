"""FlowCore Storage — EventRepository.

Persists MarketEvents (Sprint 18's runtime/observers/) so the Macro Score
Engine (Sprint 19) has real history to compute against. Mirrors
FlowRepository's shape exactly: async-only, backed by aiosqlite, same
database file via storage.database.get_db_path().

Deliberately accepts/returns plain dicts, not runtime.observers.MarketEvent
— storage owns persistence and must not depend on runtime (the dependency
direction in this codebase runs the other way).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite

from storage.database import get_db_path


class EventRepository:
    """Async repository for the `market_events` table."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or get_db_path()
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    async def ensure_tables(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS market_events (
                    id TEXT PRIMARY KEY,
                    timestamp TIMESTAMP NOT NULL,
                    source TEXT NOT NULL,
                    category TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    event TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    payload TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_market_events_source_ts ON market_events(source, timestamp)"
            )
            await db.commit()

    async def insert_event(self, event: dict[str, Any]) -> None:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT OR IGNORE INTO market_events
                   (id, timestamp, source, category, symbol, event, severity, confidence, payload, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event["id"],
                    event["timestamp"],
                    event["source"],
                    event["category"],
                    event["symbol"],
                    event["event"],
                    event["severity"],
                    event["confidence"],
                    json.dumps(event["payload"]),
                    json.dumps(event["metadata"]),
                ),
            )
            await db.commit()

    async def list_events(
        self,
        source: str | None = None,
        since: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            clauses = []
            params: list[Any] = []
            if source is not None:
                clauses.append("source = ?")
                params.append(source)
            if since is not None:
                clauses.append("timestamp >= ?")
                params.append(since)
            where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            limit_sql = " LIMIT ?" if limit is not None else ""
            if limit is not None:
                params.append(limit)
            cursor = await db.execute(
                f"""SELECT id, timestamp, source, category, symbol, event, severity, confidence, payload, metadata
                   FROM market_events{where_sql} ORDER BY timestamp DESC{limit_sql}""",
                params,
            )
            rows = await cursor.fetchall()
            return [self._row_to_event(r) for r in rows]

    @staticmethod
    def _row_to_event(row: tuple) -> dict[str, Any]:
        return {
            "id": row[0],
            "timestamp": row[1],
            "source": row[2],
            "category": row[3],
            "symbol": row[4],
            "event": row[5],
            "severity": row[6],
            "confidence": row[7],
            "payload": json.loads(row[8]),
            "metadata": json.loads(row[9]),
        }
