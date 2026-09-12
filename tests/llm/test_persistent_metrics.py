"""Tests for runtime/llm/persistent_metrics.py -- PersistentMetricsSink."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.llm.persistent_metrics import PersistentMetricsSink  # noqa: E402


class TestPersistentMetricsSink:
    def test_writes_to_the_injected_repo(self):
        fake_repo = MagicMock()
        sink = PersistentMetricsSink(repo=fake_repo)
        sink.record_call("deepseek", "deepseek-chat", 100.0, True, None, purpose="chat", tokens=42, office_id="office-1")
        fake_repo.record_call.assert_called_once_with(
            "deepseek", "deepseek-chat", 100.0, True, None, purpose="chat", tokens=42, office_id="office-1",
        )

    def test_snapshot_reflects_in_memory_counters_like_before(self):
        fake_repo = MagicMock()
        sink = PersistentMetricsSink(repo=fake_repo)
        sink.record_call("ollama", "llama3", 50.0, True, None)
        sink.record_call("ollama", "llama3", 60.0, True, None)
        snapshot = sink.snapshot()
        assert len(snapshot) == 1
        assert snapshot[0]["provider"] == "ollama"
        assert snapshot[0]["calls"] == 2

    def test_repo_failure_never_breaks_the_call(self):
        fake_repo = MagicMock()
        fake_repo.record_call.side_effect = RuntimeError("disk full")
        sink = PersistentMetricsSink(repo=fake_repo)
        sink.record_call("deepseek", "deepseek-chat", 100.0, True, None)  # must not raise
        assert sink.snapshot()[0]["calls"] == 1

    def test_default_repo_is_a_real_llm_call_repository(self, tmp_path, monkeypatch):
        monkeypatch.setattr("storage.database.get_db_path", lambda: str(tmp_path / "t.db"))
        from storage.llm_call_repo import LLMCallRepository

        sink = PersistentMetricsSink(repo=LLMCallRepository(db_path=str(tmp_path / "t.db")))
        sink.record_call("deepseek", "deepseek-chat", 100.0, True, None, purpose="orchestrator_reasoning")

        recorded = LLMCallRepository(db_path=str(tmp_path / "t.db")).recent_calls()
        assert len(recorded) == 1
        assert recorded[0]["purpose"] == "orchestrator_reasoning"
