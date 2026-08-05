"""Persisted agent task history.

Stores agent run results in ~/.flowcore/agent_history.json
so results survive daemon restarts.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


_STORE_PATH = Path.home() / ".flowcore" / "agent_history.json"
_MAX_ENTRIES = 500


@dataclass
class AgentTaskRecord:
    id: str
    agent: str
    status: str          # pending | running | completed | failed
    context: dict
    result: dict | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at and self.finished_at:
            return round(self.finished_at - self.started_at, 3)
        return None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["duration_seconds"] = self.duration_seconds
        return d

    @classmethod
    def new(cls, agent: str, context: dict | None = None) -> "AgentTaskRecord":
        return cls(
            id=uuid.uuid4().hex[:16],
            agent=agent,
            status="pending",
            context=context or {},
        )


class AgentTaskStore:
    """Thread-safe persisted store for agent task history."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _STORE_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def _save(self, records: list[dict]) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(records[-_MAX_ENTRIES:], indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def save(self, record: AgentTaskRecord) -> None:
        records = self._load()
        existing_ids = {r["id"] for r in records}
        if record.id in existing_ids:
            records = [r if r["id"] != record.id else record.to_dict() for r in records]
        else:
            records.append(record.to_dict())
        self._save(records)

    def get(self, task_id: str) -> AgentTaskRecord | None:
        for r in self._load():
            if r["id"] == task_id:
                return self._from_dict(r)
        return None

    def list_all(self, limit: int = 50, agent: str | None = None) -> list[AgentTaskRecord]:
        records = self._load()
        if agent:
            records = [r for r in records if r.get("agent") == agent]
        return [self._from_dict(r) for r in records[-limit:]]

    def clear(self) -> int:
        records = self._load()
        count = len(records)
        self._save([])
        return count

    @staticmethod
    def _from_dict(d: dict) -> AgentTaskRecord:
        return AgentTaskRecord(
            id=d["id"],
            agent=d["agent"],
            status=d["status"],
            context=d.get("context", {}),
            result=d.get("result"),
            error=d.get("error"),
            created_at=d.get("created_at", 0.0),
            started_at=d.get("started_at"),
            finished_at=d.get("finished_at"),
        )
