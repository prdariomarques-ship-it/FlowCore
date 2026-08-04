"""Tests for Sprint 14 — AgentTaskStore, AgentRunner."""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── AgentTaskRecord ────────────────────────────────────────────────────────────

class TestAgentTaskRecord:
    def test_new_creates_record(self):
        from agents.task_store import AgentTaskRecord
        r = AgentTaskRecord.new("health")
        assert r.agent == "health"
        assert r.status == "pending"
        assert len(r.id) == 16

    def test_new_with_context(self):
        from agents.task_store import AgentTaskRecord
        r = AgentTaskRecord.new("health", {"key": "value"})
        assert r.context == {"key": "value"}

    def test_duration_none_when_not_finished(self):
        from agents.task_store import AgentTaskRecord
        r = AgentTaskRecord.new("health")
        assert r.duration_seconds is None

    def test_duration_computed(self):
        from agents.task_store import AgentTaskRecord
        r = AgentTaskRecord.new("health")
        r.started_at = 1000.0
        r.finished_at = 1002.5
        assert r.duration_seconds == pytest.approx(2.5)

    def test_to_dict_has_duration(self):
        from agents.task_store import AgentTaskRecord
        r = AgentTaskRecord.new("health")
        r.started_at = 1000.0
        r.finished_at = 1001.0
        d = r.to_dict()
        assert d["duration_seconds"] == pytest.approx(1.0)
        assert "id" in d
        assert "status" in d


# ── AgentTaskStore ─────────────────────────────────────────────────────────────

class TestAgentTaskStore:
    def _store(self, tmp_path):
        from agents.task_store import AgentTaskStore
        return AgentTaskStore(path=tmp_path / "history.json")

    def test_save_and_get(self, tmp_path):
        from agents.task_store import AgentTaskRecord
        store = self._store(tmp_path)
        r = AgentTaskRecord.new("health")
        r.status = "completed"
        r.result = {"status": "ok"}
        store.save(r)
        loaded = store.get(r.id)
        assert loaded is not None
        assert loaded.agent == "health"
        assert loaded.status == "completed"

    def test_get_unknown_returns_none(self, tmp_path):
        store = self._store(tmp_path)
        assert store.get("doesnotexist") is None

    def test_list_all_empty(self, tmp_path):
        store = self._store(tmp_path)
        assert store.list_all() == []

    def test_list_all_returns_records(self, tmp_path):
        from agents.task_store import AgentTaskRecord
        store = self._store(tmp_path)
        for i in range(3):
            r = AgentTaskRecord.new(f"agent{i}")
            store.save(r)
        records = store.list_all()
        assert len(records) == 3

    def test_list_agent_filter(self, tmp_path):
        from agents.task_store import AgentTaskRecord
        store = self._store(tmp_path)
        r1 = AgentTaskRecord.new("health")
        r2 = AgentTaskRecord.new("doctor")
        store.save(r1)
        store.save(r2)
        records = store.list_all(agent="health")
        assert len(records) == 1
        assert records[0].agent == "health"

    def test_update_existing_record(self, tmp_path):
        from agents.task_store import AgentTaskRecord
        store = self._store(tmp_path)
        r = AgentTaskRecord.new("health")
        store.save(r)
        r.status = "completed"
        r.result = {"data": 42}
        store.save(r)
        records = store.list_all()
        assert len(records) == 1
        assert records[0].status == "completed"

    def test_clear(self, tmp_path):
        from agents.task_store import AgentTaskRecord
        store = self._store(tmp_path)
        for _ in range(5):
            store.save(AgentTaskRecord.new("x"))
        cleared = store.clear()
        assert cleared == 5
        assert store.list_all() == []

    def test_atomic_save(self, tmp_path):
        from agents.task_store import AgentTaskRecord
        store = self._store(tmp_path)
        r = AgentTaskRecord.new("health")
        store.save(r)
        # tmp file should not remain
        assert not (tmp_path / "history.tmp").exists()
        assert (tmp_path / "history.json").exists()


# ── AgentRunner ────────────────────────────────────────────────────────────────

class TestAgentRunner:
    def _runner(self, tmp_path, require_passport=False):
        from agents.runner import AgentRunner
        from agents.task_store import AgentTaskStore
        return AgentRunner(
            store=AgentTaskStore(path=tmp_path / "history.json"),
            require_passport=require_passport,
        )

    def test_list_agents_includes_health(self, tmp_path):
        runner = self._runner(tmp_path)
        names = [a["name"] for a in runner.list_agents()]
        assert "health" in names

    def test_run_health_sync(self, tmp_path):
        runner = self._runner(tmp_path)
        record = runner.run_sync("health")
        assert record.status == "completed"
        assert record.result is not None
        assert record.result["status"] == "ok"

    def test_run_unknown_agent_fails(self, tmp_path):
        runner = self._runner(tmp_path)
        record = runner.run_sync("nonexistent_agent_xyz")
        assert record.status == "failed"
        assert "not found" in record.error

    def test_result_persisted(self, tmp_path):
        from agents.task_store import AgentTaskStore
        store = AgentTaskStore(path=tmp_path / "history.json")
        runner = self._runner(tmp_path)
        record = runner.run_sync("health")
        loaded = store.get(record.id)
        assert loaded is not None
        assert loaded.status == "completed"

    def test_duration_recorded(self, tmp_path):
        runner = self._runner(tmp_path)
        record = runner.run_sync("health")
        assert record.duration_seconds is not None
        assert record.duration_seconds >= 0

    def test_register_custom_agent(self, tmp_path):
        from agents.base import BaseAgent
        runner = self._runner(tmp_path)

        class PingAgent(BaseAgent):
            name = "ping"
            description = "pong"
            async def run(self, context=None):
                return {"status": "ok", "data": "pong"}

        runner.register(PingAgent())
        record = runner.run_sync("ping")
        assert record.status == "completed"
        assert record.result["data"] == "pong"

    def test_passport_failure_marks_task_failed(self, tmp_path):
        runner = self._runner(tmp_path, require_passport=True)
        with patch.object(runner, "_check_passport", return_value="invalid passport"):
            record = runner.run_sync("health")
        assert record.status == "failed"
        assert "invalid passport" in record.error

    def test_passport_ok_allows_run(self, tmp_path):
        runner = self._runner(tmp_path, require_passport=True)
        with patch.object(runner, "_check_passport", return_value=None):
            record = runner.run_sync("health")
        assert record.status == "completed"

    async def _run_async(self, runner, name):
        return await runner.run(name)

    def test_async_run(self, tmp_path):
        runner = self._runner(tmp_path)
        record = asyncio.run(runner.run("health"))
        assert record.status == "completed"


# ── MCP tool tests (agent_run, agent_list, agent_history) ─────────────────────

class TestMCPAgentTools:
    def _dispatch(self, name, args=None):
        from flowcore_mcp.tools import dispatch
        return dispatch(name, args or {})

    def test_agent_list_ok(self):
        result = self._dispatch("agent_list")
        assert result.is_error is False
        import json
        data = json.loads(result.content[0].text)
        assert "agents" in data
        assert any(a["name"] == "health" for a in data["agents"])

    def test_agent_run_health(self):
        result = self._dispatch("agent_run", {"agent_name": "health"})
        assert result.is_error is False
        import json
        data = json.loads(result.content[0].text)
        assert data["status"] == "completed"

    def test_agent_run_unknown(self):
        result = self._dispatch("agent_run", {"agent_name": "no_such_agent"})
        assert result.is_error is False  # record is returned, status=failed
        import json
        data = json.loads(result.content[0].text)
        assert data["status"] == "failed"

    def test_agent_run_requires_name(self):
        result = self._dispatch("agent_run", {})
        assert result.is_error is True

    def test_agent_history_ok(self):
        # Run something first so history is non-empty
        self._dispatch("agent_run", {"agent_name": "health"})
        result = self._dispatch("agent_history", {"limit": 5})
        assert result.is_error is False
        import json
        data = json.loads(result.content[0].text)
        assert "tasks" in data
