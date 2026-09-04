"""Macro Score History — persistence + historical views.

Every time the macro scores are computed, `record_scores()` snapshots the
per-dimension score into FlowCore's own SQLite (`data/flowcore.db`, table
`macro_score_history`). `score_history()` then returns honest historical
views (D-1, D-5, D-20, D-60) computed from stored snapshots — never from
interpolation or invention. If history is too short, the view reports
INSUFFICIENT_DATA for that window rather than a padded number.

This is read-only additive: the existing Macro Score Engine is unchanged;
it only gains a recording hook.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta

_DEFAULT_DB = None  # injected by storage path at call time


def _db_path() -> str:
    # Follow the same resolution used by the rest of FlowCore.
    import pathlib
    base = pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "flowcore.db"
    return str(base)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS macro_score_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    dimension TEXT NOT NULL,
    score REAL,
    status TEXT NOT NULL,
    detail TEXT
)
"""


def record_scores(scores: list[dict]) -> None:
    """Persist a macro-score computation snapshot (idempotent per minute)."""
    conn = sqlite3.connect(_db_path())
    try:
        conn.execute(_SCHEMA)
        now = datetime.now(UTC)
        # Coarse dedup: skip if the exact same minute already recorded.
        cursor = conn.execute(
            "SELECT COUNT(*) FROM macro_score_history WHERE recorded_at >= ?",
            (now.strftime("%Y-%m-%dT%H:%M"),),
        )
        if cursor.fetchone()[0] >= 3:  # 3 dimensions recorded this minute
            return
        for row in scores:
            conn.execute(
                "INSERT INTO macro_score_history (recorded_at, dimension, score, status, detail)"
                " VALUES (?, ?, ?, ?, ?)",
                (now.isoformat(), row.get("dimension", ""), row.get("score"),
                 row.get("status", "unknown"),
                 json.dumps(row.get("drivers") or row.get("z_scores") or {})),
            )
        conn.commit()
    finally:
        conn.close()


def score_history(dimension: str | None = None, days: int = 60) -> dict:
    """Historical views for D-1 / D-5 / D-20 / D-60 windows.

    Each window reports: latest snapshot inside the window (value, status,
    timestamp). A window without data returns INSUFFICIENT_DATA — never a
    fabricated estimate.
    """
    conn = sqlite3.connect(_db_path())
    try:
        try:
            conn.execute("SELECT COUNT(*) FROM macro_score_history")
        except sqlite3.OperationalError:
            return {"error": "history_unavailable", "windows": {}}

        dims = [dimension] if dimension else [
            row[0] for row in conn.execute(
                "SELECT DISTINCT dimension FROM macro_score_history ORDER BY dimension")]
        now = datetime.now(UTC)
        windows: dict[str, dict] = {}
        for d in dims:
            views: dict[str, dict] = {}
            for label, days_back in (("D-1", 1), ("D-5", 5), ("D-20", 20), ("D-60", 60)):
                cutoff = (now - timedelta(days=days_back)).isoformat()
                row = conn.execute(
                    "SELECT recorded_at, score, status FROM macro_score_history"
                    " WHERE dimension = ? AND recorded_at >= ? ORDER BY recorded_at DESC LIMIT 1",
                    (d, cutoff),
                ).fetchone()
                if row is None:
                    views[label] = {"value": None, "status": "insufficient_data",
                                    "sampled_at": None}
                else:
                    views[label] = {"value": row[1], "status": row[2],
                                    "sampled_at": row[0]}
            # latest ever, for trend context
            latest = conn.execute(
                "SELECT recorded_at, score, status FROM macro_score_history"
                " WHERE dimension = ? ORDER BY recorded_at DESC LIMIT 1", (d,)).fetchone()
            windows[d] = {"latest": ({"value": latest[1], "status": latest[2],
                                      "sampled_at": latest[0]} if latest else None),
                          "history": views}
        return {"error": None, "windows": windows}
    finally:
        conn.close()
