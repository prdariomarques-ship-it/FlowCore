"""FlowCore — Persistent checkpoint storage.

Tasks write checkpoints to disk before each I/O operation so they can
be resumed after Android kills the process. The checkpoint survives
app restarts and is read back on the next boot cycle.

Usage::

    cp = Checkpoint("sync_job")
    cp.save({"offset": 42, "last_file": "notes.md"})

    # On next boot:
    state = cp.load()
    if state:
        offset = state["offset"]   # resume from 42
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


_CHECKPOINT_DIR = Path.home() / ".flowcore" / "checkpoints"


class Checkpoint:
    """Read/write a single task's checkpoint file."""

    def __init__(self, task_id: str) -> None:
        if not task_id or "/" in task_id:
            raise ValueError(f"Invalid task_id: {task_id!r}")
        self.task_id = task_id
        self._path = _CHECKPOINT_DIR / f"{task_id}.json"

    def save(self, state: dict[str, Any]) -> None:
        """Persist *state* atomically to disk."""
        _CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "task_id": self.task_id,
            "saved_at": time.time(),
            "state": state,
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        tmp.replace(self._path)  # atomic on POSIX

    def load(self) -> dict[str, Any] | None:
        """Return the saved state dict, or None if no checkpoint exists."""
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text())
            return data.get("state")
        except Exception:
            return None

    def clear(self) -> None:
        """Delete the checkpoint file."""
        self._path.unlink(missing_ok=True)

    def exists(self) -> bool:
        return self._path.exists()

    def metadata(self) -> dict[str, Any]:
        """Return full checkpoint record (task_id, saved_at, state)."""
        if not self._path.exists():
            return {"task_id": self.task_id, "exists": False}
        try:
            data = json.loads(self._path.read_text())
            return {**data, "exists": True}
        except Exception:
            return {"task_id": self.task_id, "exists": True, "corrupt": True}


class CheckpointStore:
    """Enumerate and bulk-manage all checkpoints."""

    @staticmethod
    def list_all() -> list[dict[str, Any]]:
        """Return metadata for every checkpoint on disk."""
        if not _CHECKPOINT_DIR.exists():
            return []
        return [Checkpoint(p.stem).metadata() for p in sorted(_CHECKPOINT_DIR.glob("*.json"))]

    @staticmethod
    def clear_all() -> int:
        """Delete all checkpoints. Returns count deleted."""
        count = 0
        for p in _CHECKPOINT_DIR.glob("*.json"):
            p.unlink(missing_ok=True)
            count += 1
        return count
