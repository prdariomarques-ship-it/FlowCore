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

The LLM Router (service.py's _llm_router) is still one process-wide
instance shared by every office on this install -- but callers that know
which office a call is for (agents/orchestrator.py's autonomous
reasoning) now thread office_id through LLMRequest.metadata, so calls
made on an office's behalf are attributed to it here; a call with no
office_id in context (e.g. the interactive /api/ask chat) is recorded
with office_id=NULL and only shows up in the global summary, never
double-counted into an office's view.

tokens comes straight from each provider's own API response (e.g.
DeepSeek's `usage.total_tokens`) -- real, not estimated, despite
LLMResponse's `tokens_estimated` field name (kept for backward
compatibility; every current provider populates it with an exact count
or leaves it None, never a guess). Deliberately no cost-in-dollars field:
provider pricing changes over time and this codebase has no verified,
current price table -- inventing one would mean showing a wrong-looking
dollar figure as if authoritative, exactly what this project's own
"never fabricate" rule (see agents/orchestrator.py's docstring) exists
to prevent. Token counts are real and auditable on their own.
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
            self._ensure_attribution_columns(db)
            db.commit()

    @staticmethod
    def _ensure_attribution_columns(db: sqlite3.Connection) -> None:
        """tokens/office_id added after the initial `llm_calls` table
        shipped -- migrate in place, same convention as
        storage/tenant_repo.py's _ensure_session_columns. Existing rows
        get NULL for both, which is honest: FlowCore genuinely didn't
        record a token count or an office attribution for calls made
        before this migration, not zero."""
        existing = {row[1] for row in db.execute("PRAGMA table_info(llm_calls)").fetchall()}
        if "tokens" not in existing:
            db.execute("ALTER TABLE llm_calls ADD COLUMN tokens INTEGER")
        if "office_id" not in existing:
            db.execute("ALTER TABLE llm_calls ADD COLUMN office_id TEXT")

    def record_call(
        self,
        provider: str,
        model: str,
        latency_ms: float,
        success: bool,
        error: str | None,
        purpose: str | None = None,
        tokens: int | None = None,
        office_id: str | None = None,
    ) -> None:
        self.ensure_tables()
        with sqlite3.connect(self._db_path, timeout=5) as db:
            db.execute(
                "INSERT INTO llm_calls "
                "(provider, model, purpose, latency_ms, success, error, created_at, tokens, office_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (provider, model, purpose, latency_ms, int(success), error, time.time(), tokens, office_id),
            )
            db.commit()

    def summary(self, since_seconds: float, office_id: str | None = None) -> dict[str, Any]:
        """Aggregate stats for calls in the last `since_seconds` -- total
        calls, success/failure split, avg latency, total tokens, and a
        breakdown by provider and by purpose. Used for the "Hoje / 7 dias
        / 30 dias" views (§19). `office_id` scopes to calls attributed to
        that office; omit for the install-wide total (includes calls with
        no office attribution, e.g. the interactive chat)."""
        self.ensure_tables()
        cutoff = time.time() - since_seconds
        office_clause = " AND office_id = ?" if office_id is not None else ""
        params: tuple = (cutoff, office_id) if office_id is not None else (cutoff,)
        with sqlite3.connect(self._db_path, timeout=5) as db:
            db.row_factory = sqlite3.Row
            total_row = db.execute(
                "SELECT COUNT(*) AS n, SUM(success) AS ok, AVG(latency_ms) AS avg_latency, SUM(tokens) AS total_tokens "
                f"FROM llm_calls WHERE created_at >= ?{office_clause}",
                params,
            ).fetchone()
            by_provider = db.execute(
                "SELECT provider, COUNT(*) AS n, SUM(success) AS ok, "
                "AVG(latency_ms) AS avg_latency, SUM(tokens) AS total_tokens "
                f"FROM llm_calls WHERE created_at >= ?{office_clause} GROUP BY provider",
                params,
            ).fetchall()
            by_purpose = db.execute(
                "SELECT COALESCE(purpose, 'unknown') AS purpose, COUNT(*) AS n "
                f"FROM llm_calls WHERE created_at >= ?{office_clause} GROUP BY purpose",
                params,
            ).fetchall()

        total = total_row["n"] or 0
        return {
            "total_calls": total,
            "successful_calls": total_row["ok"] or 0,
            "failed_calls": total - (total_row["ok"] or 0),
            "avg_latency_ms": total_row["avg_latency"],
            "total_tokens": total_row["total_tokens"] or 0,
            "by_provider": [
                {
                    "provider": r["provider"],
                    "calls": r["n"],
                    "successes": r["ok"],
                    "avg_latency_ms": r["avg_latency"],
                    "total_tokens": r["total_tokens"] or 0,
                }
                for r in by_provider
            ],
            "by_purpose": [{"purpose": r["purpose"], "calls": r["n"]} for r in by_purpose],
        }

    def recent_calls(self, limit: int = 50, office_id: str | None = None) -> list[dict[str, Any]]:
        self.ensure_tables()
        query = "SELECT * FROM llm_calls"
        params: tuple = ()
        if office_id is not None:
            query += " WHERE office_id = ?"
            params = (office_id,)
        query += " ORDER BY created_at DESC LIMIT ?"
        params = (*params, limit)
        with sqlite3.connect(self._db_path, timeout=5) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(query, params).fetchall()
        return [dict(r) for r in rows]
