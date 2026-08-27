"""Memory Engine — persistent structured memory with full provenance.

Every memory entry records:
- content  : the fact / preference / context
- origin   : where it came from (user_input | inference | feedback | external)
- source   : specific source identifier (e.g. "chat", "portfolio_review")
- scope    : lifetime ("session" | "persistent" | "until:<ISO date>")
- tags     : searchable labels
- created_at / updated_at / confidence
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

_MEMORY_FILE = Path.home() / ".flowcore" / "memory.json"

ORIGINS = ("user_input", "inference", "feedback", "external", "system")
SCOPES  = ("session", "persistent")


@dataclass
class MemoryEntry:
    id: str
    content: str
    origin: str          # one of ORIGINS
    source: str          # e.g. "chat", "market_brief", "user"
    scope: str           # "session" | "persistent" | "until:YYYY-MM-DD"
    tags: list[str]      = field(default_factory=list)
    confidence: float    = 1.0
    created_at: float    = field(default_factory=time.time)
    updated_at: float    = field(default_factory=time.time)
    invalidated: bool    = False
    invalidated_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MemoryEntry":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def is_expired(self) -> bool:
        if self.scope.startswith("until:"):
            try:
                import datetime
                cutoff = datetime.date.fromisoformat(self.scope[6:])
                return datetime.date.today() > cutoff
            except ValueError:
                return False
        return False


def _make_id(content: str, source: str) -> str:
    key = f"{source}:{content[:200]}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


class MemoryEngine:
    """Persistent memory store with provenance, tagging and invalidation."""

    def __init__(self, path: Path = _MEMORY_FILE) -> None:
        self._path = path
        self._entries: dict[str, MemoryEntry] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                self._entries = {k: MemoryEntry.from_dict(v) for k, v in data.items()}
            except Exception:
                self._entries = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(
            {k: v.to_dict() for k, v in self._entries.items()},
            indent=2, ensure_ascii=False,
        ))

    # ── write ────────────────────────────────────────────────────────────────

    def remember(
        self,
        content: str,
        *,
        origin: str = "user_input",
        source: str = "chat",
        scope: str = "persistent",
        tags: list[str] | None = None,
        confidence: float = 1.0,
    ) -> MemoryEntry:
        if origin not in ORIGINS:
            raise ValueError(f"origin must be one of {ORIGINS}")
        entry_id = _make_id(content, source)
        existing = self._entries.get(entry_id)
        if existing and not existing.invalidated:
            existing.updated_at = time.time()
            existing.confidence = confidence
            if tags:
                existing.tags = list(set(existing.tags + tags))
            self._save()
            return existing
        entry = MemoryEntry(
            id=entry_id,
            content=content,
            origin=origin,
            source=source,
            scope=scope,
            tags=tags or [],
            confidence=confidence,
        )
        self._entries[entry_id] = entry
        self._save()
        return entry

    def invalidate(self, entry_id: str, reason: str = "") -> bool:
        entry = self._entries.get(entry_id)
        if entry is None:
            return False
        entry.invalidated = True
        entry.invalidated_reason = reason
        entry.updated_at = time.time()
        self._save()
        return True

    def delete(self, entry_id: str) -> bool:
        if entry_id in self._entries:
            del self._entries[entry_id]
            self._save()
            return True
        return False

    # ── read ─────────────────────────────────────────────────────────────────

    def search(
        self,
        query: str = "",
        *,
        tags: list[str] | None = None,
        origin: str | None = None,
        include_invalidated: bool = False,
        limit: int = 20,
    ) -> list[MemoryEntry]:
        results = []
        q = query.lower()
        for entry in self._entries.values():
            if entry.is_expired():
                continue
            if not include_invalidated and entry.invalidated:
                continue
            if origin and entry.origin != origin:
                continue
            if tags and not set(tags).intersection(entry.tags):
                continue
            if q and q not in entry.content.lower():
                continue
            results.append(entry)
        results.sort(key=lambda e: -e.updated_at)
        return results[:limit]

    def get(self, entry_id: str) -> MemoryEntry | None:
        return self._entries.get(entry_id)

    def recent(self, n: int = 10) -> list[MemoryEntry]:
        active = [e for e in self._entries.values() if not e.invalidated and not e.is_expired()]
        return sorted(active, key=lambda e: -e.updated_at)[:n]

    def stats(self) -> dict[str, Any]:
        total = len(self._entries)
        active = sum(1 for e in self._entries.values() if not e.invalidated and not e.is_expired())
        by_origin: dict[str, int] = {}
        for e in self._entries.values():
            by_origin[e.origin] = by_origin.get(e.origin, 0) + 1
        return {"total": total, "active": active, "by_origin": by_origin}


_memory: MemoryEngine | None = None


def get_memory() -> MemoryEngine:
    global _memory
    if _memory is None:
        _memory = MemoryEngine()
    return _memory
