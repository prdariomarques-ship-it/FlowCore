"""FlowCore Storage — LLMCallRepository.

Persisted history of every LLM Router call (provider, model, latency,
success/failure, purpose) — the "custo de IA" / observability data the
Agent Runtime architecture calls for (§18-19): without this, cost and
call history reset every time `flowcore.py serve` restarts, exactly the
limitation runtime/llm/metrics.py's own InMemoryMetrics docstring flags
("swapping in a persisted table-backed implementation later is a pure
addition").

Plain sync sqlite3, not aiosqlite: this is written from
runtime/llm/persistent_metrics.py's PersistentMetricsSink.record_call(),
which MetricsSink's interface (runtime/llm/metrics.py) defines as a sync
method — callers already run LLMRouter.generate() itself inside
asyncio.to_thread(), so a quick sync sqlite3 connection here never blocks
the event loop. Same database file as every other repository
(storage.database.get_db_path()) — SQLite's own locking handles the mixed
sync/aiosqlite access safely for this low-frequency, single-row-insert
workload.

Deliberately NOT office-scoped yet: the LLM Router (service.py's
_llm_router) is one process-wide instance shared by every office on this
install, the same way runtime/telegram.py's TELEGRAM_BOT_TOKEN is one
shared bot. Threading office_id through LLMRequest/LLMResponse/MetricsSink
would be a real, separate change -- not invented here just to make this
table look more complete than the call chain actually supports today.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from storage.database import get_db_path

_DAY_SECONDS = 86400


class LLMCallRepository:
    """Sync repository for the `llm_calls` table."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or get_db_path()
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    def ensure_tables(self) -> None:
        with sqlite3.connect(self._db_path, timeout=5) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS llm_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    purpose TEXT,
                    latency_ms REAL NOT NULL,
                    success INTEGER NOT NULL,
                    error TEXT,
                    created_at REAL NOT NULL
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_llm_calls_created ON llm_calls(created_at)")
            db.commit()

    def record_call(
        self, provider: str, model: str, latency_ms: float, success: bool, error: str | None,
        purpose: str | None = None,
    ) -> None:
        self.ensure_tables()
        with sqlite3.connect(self._db_path, timeout=5) as db:
            db.execute(
                "INSERT INTO llm_calls (provider, model, purpose, latency_ms, success, error, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (provider, model, purpose, latency_ms, int(success), error, time.time()),
            )
            db.commit()

    def summary(self, since_seconds: float) -> dict[str, Any]:
        """Aggregate stats for calls in the last `since_seconds` -- total
        calls, success/failure split, avg latency, and a breakdown by
        provider and by purpose. Used for the "Hoje / 7 dias / 30 dias"
        views (§19)."""
        self.ensure_tables()
        cutoff = time.time() - since_seconds
        with sqlite3.connect(self._db_path, timeout=5) as db:
            db.row_factory = sqlite3.Row
            total_row = db.execute(
                "SELECT COUNT(*) AS n, SUM(success) AS ok, AVG(latency_ms) AS avg_latency "
                "FROM llm_calls WHERE created_at >= ?",
                (cutoff,),
            ).fetchone()
            by_provider = db.execute(
                "SELECT provider, COUNT(*) AS n, SUM(success) AS ok, AVG(latency_ms) AS avg_latency "
                "FROM llm_calls WHERE created_at >= ? GROUP BY provider",
                (cutoff,),
            ).fetchall()
            by_purpose = db.execute(
                "SELECT COALESCE(purpose, 'unknown') AS purpose, COUNT(*) AS n "
                "FROM llm_calls WHERE created_at >= ? GROUP BY purpose",
                (cutoff,),
            ).fetchall()

        total = total_row["n"] or 0
        return {
            "total_calls": total,
            "successful_calls": total_row["ok"] or 0,
            "failed_calls": total - (total_row["ok"] or 0),
            "avg_latency_ms": total_row["avg_latency"],
            "by_provider": [
                {"provider": r["provider"], "calls": r["n"], "successes": r["ok"], "avg_latency_ms": r["avg_latency"]}
                for r in by_provider
            ],
            "by_purpose": [{"purpose": r["purpose"], "calls": r["n"]} for r in by_purpose],
        }

    def recent_calls(self, limit: int = 50) -> list[dict[str, Any]]:
        self.ensure_tables()
        with sqlite3.connect(self._db_path, timeout=5) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT * FROM llm_calls ORDER BY created_at DESC LIMIT ?", (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
