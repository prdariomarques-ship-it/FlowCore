"""FlowCore Storage — DocumentRepository.

Centralises every SQLite operation on the `documents` table.
Previously these were duplicated inline across 8+ functions in flowcore.py.

Async-only: every caller (CLI, FastAPI, MCP) awaits these methods
directly. There used to be `*_sync()` convenience wrappers that called
`asyncio.run()` internally — they broke whenever invoked from a caller
that already had an event loop running (FastAPI, MCP), which happened
twice in Sprint 13. Removed rather than patched around again; the CLI
now runs its document-touching commands via `asyncio.run()` at the
top-level dispatch point instead (see flowcore.py's `main()`).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite

from storage.database import get_db_path


class DocumentRepository:
    """Async repository for the `documents` table."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or get_db_path()
        # Ensure the parent directory exists before any connection attempt.
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    # ── Schema ──────────────────────────────────────────────────────────────

    async def ensure_table(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()

    # ── Write ────────────────────────────────────────────────────────────────

    async def insert(self, title: str, content: str, source: str = "") -> int:
        await self.ensure_table()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "INSERT INTO documents (title, content, source) VALUES (?, ?, ?)",
                (title, content, source),
            )
            await db.commit()
            return cursor.lastrowid

    # ── Read ─────────────────────────────────────────────────────────────────

    async def list_all(self) -> list[dict[str, Any]]:
        await self.ensure_table()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT id, title, source, created_at FROM documents ORDER BY created_at DESC"
            )
            rows = await cursor.fetchall()
            return [
                {"id": r[0], "title": r[1], "source": r[2], "created_at": r[3]}
                for r in rows
            ]

    async def get_by_id(self, doc_id: int) -> dict[str, Any] | None:
        await self.ensure_table()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT id, title, content, created_at FROM documents WHERE id = ?",
                (doc_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return {"id": row[0], "title": row[1], "content": row[2], "created_at": row[3]}

    async def search(self, query: str) -> list[dict[str, Any]]:
        await self.ensure_table()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT id, title, content FROM documents WHERE title LIKE ? OR content LIKE ?",
                (f"%{query}%", f"%{query}%"),
            )
            rows = await cursor.fetchall()
            return [{"id": r[0], "title": r[1], "content": r[2]} for r in rows]

    async def list_recent(self, limit: int = 5) -> list[dict[str, Any]]:
        await self.ensure_table()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT title, content, created_at FROM documents ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [{"title": r[0], "content": r[1], "created_at": r[2]} for r in rows]

    async def count(self) -> int:
        await self.ensure_table()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM documents")
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def count_by_source(self, *sources: str) -> int:
        await self.ensure_table()
        placeholders = ",".join("?" for _ in sources)
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                f"SELECT COUNT(*) FROM documents WHERE source IN ({placeholders})",
                sources,
            )
            row = await cursor.fetchone()
            return row[0] if row else 0
