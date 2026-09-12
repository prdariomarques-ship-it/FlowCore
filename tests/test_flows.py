"""Tests for Sprint 16 — FlowStore, FlowRunner, Flow MCP tools, Flow API."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── FlowStep / Flow / FlowRun ─────────────────────────────────────────────────

class TestFlowSchema:
    def test_flow_step_to_dict(self):
        from flows.schema import FlowStep
        s = FlowStep(agent="health", context={"key": "val"})
        d = s.to_dict()
        assert d["agent"] == "health"
        assert d["context"] == {"key": "val"}

    def test_flow_step_from_dict(self):
        from flows.schema import FlowStep
        s = FlowStep.from_dict({"agent": "doctor"})
        assert s.agent == "doctor"
        assert s.context == {}

    def test_flow_new(self):
        from flows.schema import Flow
        f = Flow.new("Test", steps=[{"agent": "health"}])
        assert f.name == "Test"
        assert len(f.steps) == 1
        assert f.steps[0].agent == "health"
        assert len(f.id) == 12

    def test_flow_new_no_steps(self):
        from flows.schema import Flow
        f = Flow.new("Empty")
        assert f.steps == []

    def test_flow_to_dict_roundtrip(self):
        from flows.schema import Flow
        f = Flow.new("MyFlow", steps=[{"agent": "health"}, {"agent": "doctor"}], description="test")
        d = f.to_dict()
        f2 = Flow.from_dict(d)
        assert f2.id == f.id
        assert f2.name == f.name
        assert len(f2.steps) == 2
        assert f2.description == "test"

    def test_flow_run_new(self):
        from flows.schema import Flow, FlowRun
        f = Flow.new("Run")
        r = FlowRun.new(f)
        assert r.flow_id == f.id
        assert r.flow_name == f.name
        assert r.status == "pending"
        assert len(r.id) == 16

    def test_flow_run_duration_none_when_not_finished(self):
        from flows.schema import Flow, FlowRun
        r = FlowRun.new(Flow.new("x"))
        assert r.duration_seconds is None

    def test_flow_run_duration_computed(self):
        from flows.schema import Flow, FlowRun
        r = FlowRun.new(Flow.new("x"))
        r.started_at = 1000.0
        r.finished_at = 1003.5
        assert r.duration_seconds == pytest.approx(3.5)

    def test_flow_run_to_dict_has_all_keys(self):
        from flows.schema import Flow, FlowRun
        r = FlowRun.new(Flow.new("x"))
        d = r.to_dict()
        for k in ("id", "flow_id", "flow_name", "status", "step_results",
                   "created_at", "duration_seconds", "error"):
            assert k in d


# ── FlowStore ─────────────────────────────────────────────────────────────────

class TestFlowStore:
    def _store(self, tmp_path):
        from flows.store import FlowStore
        return FlowStore(
            path=tmp_path / "flows.json",
            runs_path=tmp_path / "flow_runs.json",
        )

    def test_save_and_get_flow(self, tmp_path):
        from flows.schema import Flow
        store = self._store(tmp_path)
        f = Flow.new("MyFlow")
        store.save_flow(f)
        loaded = store.get_flow(f.id)
        assert loaded is not None
        assert loaded.name == "MyFlow"

    def test_get_unknown_flow_returns_none(self, tmp_path):
        store = self._store(tmp_path)
        assert store.get_flow("nonexistent") is None

    def test_list_flows_empty(self, tmp_path):
        store = self._store(tmp_path)
        assert store.list_flows() == []

    def test_list_flows_returns_all(self, tmp_path):
        from flows.schema import Flow
        store = self._store(tmp_path)
        for i in range(3):
            store.save_flow(Flow.new(f"Flow{i}"))
        assert len(store.list_flows()) == 3

    def test_delete_flow(self, tmp_path):
        from flows.schema import Flow
        store = self._store(tmp_path)
        f = Flow.new("ToDelete")
        store.save_flow(f)
        assert store.delete_flow(f.id) is True
        assert store.get_flow(f.id) is None

    def test_delete_nonexistent_returns_false(self, tmp_path):
        store = self._store(tmp_path)
        assert store.delete_flow("nope") is False

    def test_atomic_save_no_tmp_left(self, tmp_path):
        from flows.schema import Flow
        store = self._store(tmp_path)
        store.save_flow(Flow.new("A"))
        assert not (tmp_path / "flows.tmp").exists()

    def test_save_and_get_run(self, tmp_path):
        from flows.schema import Flow, FlowRun
        store = self._store(tmp_path)
        f = Flow.new("RunFlow")
        r = FlowRun.new(f)
        r.status = "completed"
        store.save_run(r)
        loaded = store.get_run(r.id)
        assert loaded is not None
        assert loaded.status == "completed"

    def test_list_runs_filter_by_flow(self, tmp_path):
        from flows.schema import Flow, FlowRun
        store = self._store(tmp_path)
        f1 = Flow.new("F1")
        f2 = Flow.new("F2")
        for _ in range(2):
            store.save_run(FlowRun.new(f1))
        store.save_run(FlowRun.new(f2))
        runs = store.list_runs(flow_id=f1.id)
        assert len(runs) == 2
        assert all(r.flow_id == f1.id for r in runs)

    def test_run_upsert(self, tmp_path):
        from flows.schema import Flow, FlowRun
        store = self._store(tmp_path)
        f = Flow.new("Upsert")
        r = FlowRun.new(f)
        store.save_run(r)
        r.status = "completed"
        store.save_run(r)
        runs = store.list_runs(flow_id=f.id)
        assert len(runs) == 1
        assert runs[0].status == "completed"


# ── FlowRunner ────────────────────────────────────────────────────────────────

class TestFlowRunner:
    def _runner(self, tmp_path):
        from flows.runner import FlowRunner
        from flows.store import FlowStore
        store = FlowStore(
            path=tmp_path / "flows.json",
            runs_path=tmp_path / "flow_runs.json",
        )
        return FlowRunner(store=store), store

    def test_run_empty_flow_completes(self, tmp_path):
        from flows.schema import Flow
        runner, store = self._runner(tmp_path)
        f = Flow.new("Empty")
        store.save_flow(f)
        run = runner.run_sync(f)
        assert run.status == "completed"
        assert run.step_results == []

    def test_run_single_step(self, tmp_path):
        from flows.schema import Flow
        runner, store = self._runner(tmp_path)
        f = Flow.new("Health", steps=[{"agent": "health"}])
        store.save_flow(f)
        run = runner.run_sync(f)
        assert run.status == "completed"
        assert len(run.step_results) == 1
        assert run.step_results[0]["agent"] == "health"
        assert run.step_results[0]["status"] == "completed"

    def test_run_multi_step(self, tmp_path):
        from flows.schema import Flow
        runner, store = self._runner(tmp_path)
        f = Flow.new("Multi", steps=[{"agent": "health"}, {"agent": "doctor"}])
        store.save_flow(f)
        run = runner.run_sync(f)
        assert run.status == "completed"
        assert len(run.step_results) == 2

    def test_run_fails_on_bad_agent(self, tmp_path):
        from flows.schema import Flow
        runner, store = self._runner(tmp_path)
        f = Flow.new("Bad", steps=[{"agent": "no_such_agent_xyz"}])
        store.save_flow(f)
        run = runner.run_sync(f)
        assert run.status == "failed"
        assert run.error is not None
        assert len(run.step_results) == 1

    def test_run_stops_on_first_failure(self, tmp_path):
        from flows.schema import Flow
        runner, store = self._runner(tmp_path)
        f = Flow.new("StopOnFail", steps=[
            {"agent": "no_such_agent_xyz"},
            {"agent": "health"},  # should not run
        ])
        store.save_flow(f)
        run = runner.run_sync(f)
        assert run.status == "failed"
        assert len(run.step_results) == 1  # stopped after first failure

    def test_run_persisted(self, tmp_path):
        from flows.schema import Flow
        runner, store = self._runner(tmp_path)
        f = Flow.new("Persist", steps=[{"agent": "health"}])
        store.save_flow(f)
        run = runner.run_sync(f)
        loaded = store.get_run(run.id)
        assert loaded is not None
        assert loaded.status == "completed"

    def test_duration_recorded(self, tmp_path):
        from flows.schema import Flow
        runner, store = self._runner(tmp_path)
        f = Flow.new("Dur", steps=[{"agent": "health"}])
        run = runner.run_sync(f)
        assert run.duration_seconds is not None
        assert run.duration_seconds >= 0

    def test_async_run(self, tmp_path):
        from flows.schema import Flow
        runner, store = self._runner(tmp_path)
        f = Flow.new("Async", steps=[{"agent": "health"}])
        run = asyncio.run(runner.run(f))
        assert run.status == "completed"


# ── Flow MCP tools ────────────────────────────────────────────────────────────

class TestMCPFlowTools:
    def _dispatch(self, name, args=None):
        from flowcore_mcp.tools import dispatch
        return dispatch(name, args or {})

    def test_flow_list_ok(self):
        result = self._dispatch("flow_list")
        assert result.is_error is False
        import json
        data = json.loads(result.content[0].text)
        assert "flows" in data

    def test_flow_create_ok(self):
        result = self._dispatch("flow_create", {
            "name": "MCP Test Flow",
            "steps": [{"agent": "health"}],
        })
        assert result.is_error is False
        import json
        data = json.loads(result.content[0].text)
        assert data["name"] == "MCP Test Flow"
        assert len(data["steps"]) == 1

    def test_flow_create_requires_name(self):
        result = self._dispatch("flow_create", {})
        assert result.is_error is True

    def test_flow_run_unknown_id(self):
        result = self._dispatch("flow_run", {"flow_id": "nonexistent_xyz"})
        assert result.is_error is True

    def test_flow_run_ok(self):
        import json
        create = self._dispatch("flow_create", {
            "name": "MCP Run Flow",
            "steps": [{"agent": "health"}],
        })
        flow_id = json.loads(create.content[0].text)["id"]
        result = self._dispatch("flow_run", {"flow_id": flow_id})
        assert result.is_error is False
        data = json.loads(result.content[0].text)
        assert data["status"] == "completed"

    def test_flow_run_requires_flow_id(self):
        result = self._dispatch("flow_run", {})
        assert result.is_error is True


# ── Flow API endpoints ────────────────────────────────────────────────────────

class TestFlowAPI:
    def _client(self):
        fastapi = pytest.importorskip("fastapi")
        httpx = pytest.importorskip("httpx")
        from fastapi.testclient import TestClient
        from api.router import create_app
        app = create_app(version="test", platform_info={"os_name": "test"})
        return TestClient(app)

    def test_list_flows_ok(self):
        r = self._client().get("/api/flows")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_flow_no_steps(self):
        r = self._client().post("/api/flows", json={"name": "API Flow"})
        assert r.status_code == 200
        data = r.json()
        assert "id" in data
        assert data["name"] == "API Flow"

    def test_create_flow_with_steps(self):
        r = self._client().post("/api/flows", json={
            "name": "Stepped Flow",
            "steps": [{"agent": "health"}],
        })
        assert r.status_code == 200
        data = r.json()
        assert len(data["steps"]) == 1

    def test_get_flow_404(self):
        r = self._client().get("/api/flows/nonexistent_xyz")
        assert r.status_code == 404

    def test_delete_flow_404(self):
        r = self._client().delete("/api/flows/nonexistent_xyz")
        assert r.status_code == 404

    def test_run_flow_404(self):
        r = self._client().post("/api/flows/nonexistent_xyz/run")
        assert r.status_code == 404

    def test_run_flow_ok(self):
        c = self._client()
        create = c.post("/api/flows", json={"name": "Run Me", "steps": [{"agent": "health"}]})
        fid = create.json()["id"]
        r = c.post(f"/api/flows/{fid}/run")
        assert r.status_code == 202
        data = r.json()
        assert data["status"] == "completed"
        assert len(data["step_results"]) == 1

    def test_list_flow_runs(self):
        c = self._client()
        create = c.post("/api/flows", json={"name": "RunHistory", "steps": [{"agent": "health"}]})
        fid = create.json()["id"]
        c.post(f"/api/flows/{fid}/run")
        r = c.get(f"/api/flows/{fid}/runs")
        assert r.status_code == 200
        assert "runs" in r.json()
        assert len(r.json()["runs"]) >= 1
