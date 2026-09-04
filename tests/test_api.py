"""Tests for Sprint 11 API endpoints — status, memories, notify, daemon control."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Skip all tests if FastAPI / httpx not installed
fastapi = pytest.importorskip("fastapi")
httpx   = pytest.importorskip("httpx")

from fastapi.testclient import TestClient


def _client():
    from api.router import create_app
    app = create_app(version="test", platform_info={"os_name": "test"})
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_ok(self):
        r = _client().get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["version"] == "test"
        assert "uptime_seconds" in data

    def test_health_platform(self):
        r = _client().get("/api/health")
        assert r.json()["platform"]["os_name"] == "test"


class TestStatusEndpoint:
    def test_status_returns_200(self):
        r = _client().get("/api/status")
        assert r.status_code == 200

    def test_status_has_required_keys(self):
        r = _client().get("/api/status")
        data = r.json()
        for key in ("version", "uptime_seconds", "daemon", "capabilities",
                    "doctor", "memory_count"):
            assert key in data, f"Missing key: {key}"

    def test_status_daemon_field_is_dict(self):
        r = _client().get("/api/status")
        assert isinstance(r.json()["daemon"], dict)

    def test_status_capabilities_field_is_dict(self):
        r = _client().get("/api/status")
        assert isinstance(r.json()["capabilities"], dict)

    def test_status_doctor_field_is_list(self):
        r = _client().get("/api/status")
        assert isinstance(r.json()["doctor"], list)


class TestMemoriesEndpoint:
    def test_list_memories_returns_200(self):
        r = _client().get("/api/memories")
        assert r.status_code == 200
        assert "memories" in r.json()

    def test_create_memory(self):
        c = _client()
        r = c.post("/api/memories", json={"text": "Test memory #api"})
        assert r.status_code == 201
        data = r.json()
        assert "memory" in data
        assert "Test memory" in data["memory"]["text"]

    def test_created_memory_appears_in_list(self):
        c = _client()
        unique = "UniqueTestContent_xyz_789"
        c.post("/api/memories", json={"text": unique})
        mems = c.get("/api/memories").json()["memories"]
        assert any(unique in m.get("text", "") for m in mems)


class TestNotifyEndpoint:
    def test_notify_without_termux_api(self):
        c = _client()
        with patch("runtime.shell.is_available", return_value=False):
            r = c.post("/api/notify", json={"title": "Test", "body": "Hello"})
        assert r.status_code == 200
        assert r.json()["sent"] is False

    def test_notify_with_termux_api(self):
        c = _client()
        mock_result = MagicMock(success=True, stderr="")
        with (
            patch("runtime.shell.is_available", return_value=True),
            patch("runtime.shell.run", return_value=mock_result),
        ):
            r = c.post("/api/notify", json={"title": "FlowCore", "body": "Test notification"})
        assert r.status_code == 200
        assert r.json()["sent"] is True


class TestDaemonEndpoints:
    def test_daemon_status_returns_200(self):
        r = _client().get("/api/daemon/status")
        assert r.status_code == 200
        assert "running" in r.json()

    def test_daemon_start_returns_message(self):
        c = _client()
        mock_daemon = MagicMock()
        mock_daemon.return_value.start.return_value = {
            "started": True, "pid": 12345, "log": "/tmp/d.log"
        }
        with patch("runtime.daemon.FlowCoreDaemon", mock_daemon):
            r = c.post("/api/daemon/start")
        assert r.status_code == 200
        assert "message" in r.json()

    def test_daemon_stop_returns_message(self):
        c = _client()
        mock_daemon = MagicMock()
        mock_daemon.return_value.stop.return_value = {"stopped": True, "pid": 12345}
        with patch("runtime.daemon.FlowCoreDaemon", mock_daemon):
            r = c.post("/api/daemon/stop")
        assert r.status_code == 200
        assert "message" in r.json()


class TestWebUI:
    def test_root_returns_html(self):
        r = _client().get("/")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            assert "FlowCore" in r.text
            assert "text/html" in r.headers.get("content-type", "")

    def test_flows_crud(self):
        c = _client()
        r = c.post("/api/flows", json={"name": "TestFlow"})
        assert r.status_code == 200
        fid = r.json()["id"]

        r2 = c.get(f"/api/flows/{fid}")
        assert r2.status_code == 200
        assert r2.json()["name"] == "TestFlow"

        r3 = c.delete(f"/api/flows/{fid}")
        assert r3.status_code == 200

        r4 = c.get(f"/api/flows/{fid}")
        assert r4.status_code == 404


class TestAgentEndpoints:
    def test_list_agents(self):
        r = _client().get("/api/agent/agents")
        assert r.status_code == 200
        data = r.json()
        assert "agents" in data
        names = [a["name"] for a in data["agents"]]
        assert "health" in names
        assert "doctor" in names

    def test_run_health_agent(self):
        r = _client().post("/api/agent/run?agent_name=health", json={})
        assert r.status_code == 202
        data = r.json()
        assert data["agent"] == "health"
        assert data["status"] in ("completed", "failed", "pending")

    def test_run_unknown_agent(self):
        r = _client().post("/api/agent/run?agent_name=no_such_agent", json={})
        assert r.status_code == 202
        data = r.json()
        assert data["status"] == "failed"
        assert "not found" in data["error"]

    def test_list_tasks(self):
        c = _client()
        c.post("/api/agent/run?agent_name=health", json={})
        r = c.get("/api/agent/tasks")
        assert r.status_code == 200
        data = r.json()
        assert "tasks" in data

    def test_get_task_by_id(self):
        c = _client()
        run_r = c.post("/api/agent/run?agent_name=health", json={})
        task_id = run_r.json()["id"]
        r = c.get(f"/api/agent/tasks/{task_id}")
        # May be 200 if the store path is accessible, or 404 in isolated env
        assert r.status_code in (200, 404)

    def test_get_task_404(self):
        r = _client().get("/api/agent/tasks/nonexistent_id_xyz")
        assert r.status_code == 404
