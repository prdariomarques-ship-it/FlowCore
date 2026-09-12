"""Tests for storage/llm_call_repo.py -- persisted LLM call history
(cost/observability data, §18-19 of the Agent Runtime architecture).

Sync repository (matches MetricsSink's sync interface) -- no
asyncio.run() wrapping needed, unlike the rest of this suite's async
repositories.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage.llm_call_repo import LLMCallRepository  # noqa: E402


def _repo(tmp_path: Path) -> LLMCallRepository:
    return LLMCallRepository(db_path=str(tmp_path / "llm_calls_test.db"))


class TestRecordCall:
    def test_record_and_recent(self, tmp_path):
        repo = _repo(tmp_path)
        repo.record_call("deepseek", "deepseek-chat", 120.5, True, None, purpose="orchestrator_reasoning")
        recent = repo.recent_calls()
        assert len(recent) == 1
        assert recent[0]["provider"] == "deepseek"
        assert recent[0]["model"] == "deepseek-chat"
        assert recent[0]["success"] == 1
        assert recent[0]["purpose"] == "orchestrator_reasoning"

    def test_records_failure_with_error(self, tmp_path):
        repo = _repo(tmp_path)
        repo.record_call("deepseek", "deepseek-chat", 50.0, False, "DeepSeek rejected the request (401)")
        recent = repo.recent_calls()
        assert recent[0]["success"] == 0
        assert "401" in recent[0]["error"]

    def test_recent_calls_most_recent_first(self, tmp_path):
        repo = _repo(tmp_path)
        with patch("time.time", return_value=100.0):
            repo.record_call("ollama", "llama3", 10.0, True, None)
        with patch("time.time", return_value=200.0):
            repo.record_call("deepseek", "deepseek-chat", 20.0, True, None)
        recent = repo.recent_calls()
        assert [r["provider"] for r in recent] == ["deepseek", "ollama"]

    def test_recent_calls_respects_limit(self, tmp_path):
        repo = _repo(tmp_path)
        for _ in range(5):
            repo.record_call("ollama", "llama3", 10.0, True, None)
        assert len(repo.recent_calls(limit=2)) == 2


class TestSummary:
    def test_empty_summary(self, tmp_path):
        repo = _repo(tmp_path)
        summary = repo.summary(since_seconds=86400)
        assert summary["total_calls"] == 0
        assert summary["successful_calls"] == 0
        assert summary["failed_calls"] == 0
        assert summary["by_provider"] == []

    def test_counts_success_and_failure(self, tmp_path):
        repo = _repo(tmp_path)
        repo.record_call("deepseek", "deepseek-chat", 100.0, True, None)
        repo.record_call("deepseek", "deepseek-chat", 100.0, False, "boom")
        summary = repo.summary(since_seconds=86400)
        assert summary["total_calls"] == 2
        assert summary["successful_calls"] == 1
        assert summary["failed_calls"] == 1

    def test_breaks_down_by_provider(self, tmp_path):
        repo = _repo(tmp_path)
        repo.record_call("deepseek", "deepseek-chat", 100.0, True, None)
        repo.record_call("ollama", "llama3", 50.0, True, None)
        repo.record_call("ollama", "llama3", 60.0, True, None)
        summary = repo.summary(since_seconds=86400)
        by_provider = {p["provider"]: p["calls"] for p in summary["by_provider"]}
        assert by_provider == {"deepseek": 1, "ollama": 2}

    def test_breaks_down_by_purpose(self, tmp_path):
        repo = _repo(tmp_path)
        repo.record_call("deepseek", "deepseek-chat", 100.0, True, None, purpose="orchestrator_reasoning")
        repo.record_call("deepseek", "deepseek-chat", 100.0, True, None, purpose="chat")
        repo.record_call("deepseek", "deepseek-chat", 100.0, True, None)  # no purpose given
        summary = repo.summary(since_seconds=86400)
        by_purpose = {p["purpose"]: p["calls"] for p in summary["by_purpose"]}
        assert by_purpose == {"orchestrator_reasoning": 1, "chat": 1, "unknown": 1}

    def test_excludes_calls_outside_the_window(self, tmp_path):
        repo = _repo(tmp_path)
        now = time.time()
        with patch("time.time", return_value=now - 10 * 86400):
            repo.record_call("deepseek", "deepseek-chat", 100.0, True, None)
        with patch("time.time", return_value=now):
            repo.record_call("deepseek", "deepseek-chat", 100.0, True, None)
        summary = repo.summary(since_seconds=86400)  # last 24h only
        assert summary["total_calls"] == 1

    def test_sums_tokens_across_calls(self, tmp_path):
        repo = _repo(tmp_path)
        repo.record_call("deepseek", "deepseek-chat", 100.0, True, None, tokens=120)
        repo.record_call("deepseek", "deepseek-chat", 100.0, True, None, tokens=80)
        summary = repo.summary(since_seconds=86400)
        assert summary["total_tokens"] == 200

    def test_tokens_none_is_not_an_error_and_sums_as_zero(self, tmp_path):
        repo = _repo(tmp_path)
        repo.record_call("deepseek", "deepseek-chat", 100.0, True, None)  # no tokens given
        summary = repo.summary(since_seconds=86400)
        assert summary["total_tokens"] == 0

    def test_by_provider_includes_total_tokens(self, tmp_path):
        repo = _repo(tmp_path)
        repo.record_call("deepseek", "deepseek-chat", 100.0, True, None, tokens=100)
        repo.record_call("deepseek", "deepseek-chat", 100.0, True, None, tokens=50)
        repo.record_call("ollama", "llama3", 50.0, True, None, tokens=10)
        summary = repo.summary(since_seconds=86400)
        by_provider = {p["provider"]: p["total_tokens"] for p in summary["by_provider"]}
        assert by_provider == {"deepseek": 150, "ollama": 10}


class TestOfficeScoping:
    def test_summary_scoped_to_one_office(self, tmp_path):
        repo = _repo(tmp_path)
        repo.record_call("deepseek", "deepseek-chat", 100.0, True, None, office_id="office-a")
        repo.record_call("deepseek", "deepseek-chat", 100.0, True, None, office_id="office-a")
        repo.record_call("deepseek", "deepseek-chat", 100.0, True, None, office_id="office-b")
        summary_a = repo.summary(since_seconds=86400, office_id="office-a")
        summary_b = repo.summary(since_seconds=86400, office_id="office-b")
        assert summary_a["total_calls"] == 2
        assert summary_b["total_calls"] == 1

    def test_no_office_id_gives_the_install_wide_total(self, tmp_path):
        repo = _repo(tmp_path)
        repo.record_call("deepseek", "deepseek-chat", 100.0, True, None, office_id="office-a")
        repo.record_call("deepseek", "deepseek-chat", 100.0, True, None)  # e.g. the interactive chat
        summary = repo.summary(since_seconds=86400)
        assert summary["total_calls"] == 2

    def test_recent_calls_scoped_to_one_office(self, tmp_path):
        repo = _repo(tmp_path)
        repo.record_call("deepseek", "deepseek-chat", 100.0, True, None, office_id="office-a")
        repo.record_call("deepseek", "deepseek-chat", 100.0, True, None, office_id="office-b")
        recent_a = repo.recent_calls(office_id="office-a")
        assert len(recent_a) == 1
        assert recent_a[0]["office_id"] == "office-a"


class TestSchemaMigration:
    def test_pre_existing_table_without_new_columns_gets_migrated(self, tmp_path):
        """Simulates a database created before tokens/office_id existed --
        a bare llm_calls table with only the original columns -- and
        confirms ensure_tables() adds both without losing existing rows."""
        import sqlite3

        db_path = str(tmp_path / "legacy.db")
        with sqlite3.connect(db_path) as db:
            db.execute("""
                CREATE TABLE llm_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL, model TEXT NOT NULL, purpose TEXT,
                    latency_ms REAL NOT NULL, success INTEGER NOT NULL, error TEXT,
                    created_at REAL NOT NULL
                )
            """)
            db.execute(
                "INSERT INTO llm_calls (provider, model, latency_ms, success, error, created_at) "
                "VALUES ('ollama', 'llama3', 10.0, 1, NULL, ?)",
                (time.time(),),
            )
            db.commit()

        repo = LLMCallRepository(db_path=db_path)
        repo.ensure_tables()
        recent = repo.recent_calls()
        assert len(recent) == 1
        assert recent[0]["tokens"] is None
        assert recent[0]["office_id"] is None

        repo.record_call("deepseek", "deepseek-chat", 50.0, True, None, tokens=99, office_id="office-a")
        recent = repo.recent_calls()
        assert recent[0]["tokens"] == 99
        assert recent[0]["office_id"] == "office-a"
