"""Tests for storage.memory_repo.MemoryRepository.

Focus: add() must never report a memory as saved when the write actually
failed -- a real, reproduced bug found during Sprint 25's Runtime deep
hardening pass (persistence failure silently swallowed, caller received
a "success" dict even though nothing was written to disk).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestMemoryRepository:
    def _repo(self, tmp_path):
        from storage.memory_repo import MemoryRepository

        return MemoryRepository(file_path=tmp_path / "memories.json")

    def test_add_persists_and_returns_memory(self, tmp_path):
        repo = self._repo(tmp_path)
        memory = repo.add("buy milk #todo")
        assert memory["text"] == "buy milk #todo"
        assert memory["topics"] == ["todo"]
        assert (tmp_path / "memories.json").exists()

    def test_add_raises_when_write_fails_instead_of_reporting_success(self, monkeypatch, tmp_path):
        """Real bug, reproduced: a write failure (permissions, disk full --
        realistic on Termux/Android) used to be caught and logged inside
        _save(), so add() still returned a normal-looking memory dict with
        no way for the caller to know it was never persisted. Now it must
        raise instead of silently losing the data."""
        if sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0):
            pytest.skip("POSIX file-permission semantics required, and root bypasses them")

        ro_dir = tmp_path / "ro"
        ro_dir.mkdir()
        ro_dir.chmod(0o500)
        try:
            from storage.memory_repo import MemoryRepository

            repo = MemoryRepository(file_path=ro_dir / "memories.json")
            with pytest.raises(OSError):
                repo.add("this must not silently vanish")
        finally:
            ro_dir.chmod(0o700)
        assert not (ro_dir / "memories.json").exists()

    def test_search_and_count_after_add(self, tmp_path):
        repo = self._repo(tmp_path)
        repo.add("first note #alpha")
        repo.add("second note #beta")
        assert repo.count() == 2
        assert len(repo.search("alpha")) == 1
        assert len(repo.search("note")) == 2
