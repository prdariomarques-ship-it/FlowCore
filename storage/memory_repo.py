"""FlowCore Storage — MemoryRepository.

Wraps the JSON-based memory store used by remember/recall/memories commands.
Isolates file-system details from the CLI presentation layer.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


class MemoryRepository:
    """Repository for memories stored as JSON in ~/.flowcore/memories.json."""

    def __init__(self, file_path: Path | None = None) -> None:
        if file_path is None:
            memories_dir = Path.home() / ".flowcore"
            memories_dir.mkdir(exist_ok=True)
            file_path = memories_dir / "memories.json"
        self._file = file_path

    # ── Persistence ──────────────────────────────────────────────────────────

    def load(self) -> list[dict[str, Any]]:
        if not self._file.exists():
            return []
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error("Error loading memories: {}", e)
            return []

    def _save(self, memories: list[dict[str, Any]]) -> None:
        try:
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(memories, f, indent=2, ensure_ascii=False)
        except IOError as e:
            logger.error("Error saving memories: {}", e)

    # ── Domain operations ────────────────────────────────────────────────────

    def add(self, text: str) -> dict[str, Any]:
        """Persist a new memory and return it."""
        memories = self.load()
        topics = [w[1:].lower() for w in text.split() if w.startswith("#") and len(w) > 1]
        memory: dict[str, Any] = {
            "text": text,
            "timestamp": datetime.now().isoformat(),
            "topics": topics,
        }
        memories.append(memory)
        self._save(memories)
        return memory

    def search(self, query: str) -> list[dict[str, Any]]:
        """Return memories matching *query* by text or topic (case-insensitive)."""
        q = query.lower().lstrip("#")
        return [m for m in self.load() if q in m.get("text", "").lower() or any(q in t for t in m.get("topics", []))]

    def count(self) -> int:
        return len(self.load())

    def list_all(self) -> list[dict[str, Any]]:
        return self.load()
