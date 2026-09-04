"""Tests for runtime.checkpoint — Checkpoint and CheckpointStore."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestCheckpoint:
    def _cp(self, task_id: str, tmpdir: Path):
        from runtime.checkpoint import Checkpoint, _CHECKPOINT_DIR
        with patch("runtime.checkpoint._CHECKPOINT_DIR", tmpdir):
            cp = Checkpoint(task_id)
            cp._path = tmpdir / f"{task_id}.json"
            return cp

    def test_save_and_load(self, tmp_path):
        from runtime.checkpoint import Checkpoint
        with patch("runtime.checkpoint._CHECKPOINT_DIR", tmp_path):
            cp = Checkpoint("job1")
            cp._path = tmp_path / "job1.json"
            cp.save({"offset": 42, "last_file": "notes.md"})
            state = cp.load()
        assert state == {"offset": 42, "last_file": "notes.md"}

    def test_load_returns_none_when_missing(self, tmp_path):
        from runtime.checkpoint import Checkpoint
        cp = Checkpoint("nonexistent")
        cp._path = tmp_path / "nonexistent.json"
        assert cp.load() is None

    def test_exists_false_before_save(self, tmp_path):
        from runtime.checkpoint import Checkpoint
        cp = Checkpoint("new_task")
        cp._path = tmp_path / "new_task.json"
        assert cp.exists() is False

    def test_exists_true_after_save(self, tmp_path):
        from runtime.checkpoint import Checkpoint
        cp = Checkpoint("saved_task")
        cp._path = tmp_path / "saved_task.json"
        cp.save({"x": 1})
        assert cp.exists() is True

    def test_clear_removes_file(self, tmp_path):
        from runtime.checkpoint import Checkpoint
        cp = Checkpoint("clearme")
        cp._path = tmp_path / "clearme.json"
        cp.save({"x": 1})
        assert cp.exists()
        cp.clear()
        assert not cp.exists()
        assert cp.load() is None

    def test_metadata_before_save(self, tmp_path):
        from runtime.checkpoint import Checkpoint
        cp = Checkpoint("meta_test")
        cp._path = tmp_path / "meta_test.json"
        meta = cp.metadata()
        assert meta["task_id"] == "meta_test"
        assert meta["exists"] is False

    def test_metadata_after_save(self, tmp_path):
        from runtime.checkpoint import Checkpoint
        cp = Checkpoint("meta_task")
        cp._path = tmp_path / "meta_task.json"
        cp.save({"k": "v"})
        meta = cp.metadata()
        assert meta["exists"] is True
        assert meta["task_id"] == "meta_task"
        assert "saved_at" in meta

    def test_save_is_atomic(self, tmp_path):
        """After save the .tmp file must not remain."""
        from runtime.checkpoint import Checkpoint
        cp = Checkpoint("atomic")
        cp._path = tmp_path / "atomic.json"
        cp.save({"n": 1})
        assert not (tmp_path / "atomic.tmp").exists()
        assert (tmp_path / "atomic.json").exists()

    def test_invalid_task_id_raises(self):
        from runtime.checkpoint import Checkpoint
        with pytest.raises(ValueError):
            Checkpoint("bad/id")

    def test_invalid_empty_task_id_raises(self):
        from runtime.checkpoint import Checkpoint
        with pytest.raises(ValueError):
            Checkpoint("")

    def test_overwrite_save(self, tmp_path):
        from runtime.checkpoint import Checkpoint
        cp = Checkpoint("overwrite")
        cp._path = tmp_path / "overwrite.json"
        cp.save({"v": 1})
        cp.save({"v": 2})
        assert cp.load() == {"v": 2}


class TestCheckpointStore:
    def test_list_all_empty(self, tmp_path):
        from runtime.checkpoint import CheckpointStore
        with patch("runtime.checkpoint._CHECKPOINT_DIR", tmp_path / "empty"):
            result = CheckpointStore.list_all()
        assert result == []

    def test_list_all_finds_saved(self, tmp_path):
        from runtime.checkpoint import Checkpoint, CheckpointStore
        cp = Checkpoint("store_task")
        cp._path = tmp_path / "store_task.json"
        cp.save({"data": True})

        with patch("runtime.checkpoint._CHECKPOINT_DIR", tmp_path):
            result = CheckpointStore.list_all()
        assert any(r["task_id"] == "store_task" for r in result)

    def test_clear_all_returns_count(self, tmp_path):
        from runtime.checkpoint import Checkpoint, CheckpointStore
        for i in range(3):
            cp = Checkpoint(f"task{i}")
            cp._path = tmp_path / f"task{i}.json"
            cp.save({"i": i})

        with patch("runtime.checkpoint._CHECKPOINT_DIR", tmp_path):
            deleted = CheckpointStore.clear_all()
        assert deleted == 3
