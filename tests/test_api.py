"""Tests for Sprint 11 API endpoints — status, memories, notify, daemon control.

Also covers Sprint 15's Flow/Execution endpoints (TestFlowsEndpoints).
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Skip all tests if FastAPI / httpx not installed
fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

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
        for key in ("version", "uptime_seconds", "daemon", "capabilities", "doctor", "memory_count"):
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

    def test_create_memory(self, tmp_path):
        # api/router.py's create_memory instantiates MemoryRepository() with no
        # path override, which defaults to the real ~/.flowcore/memories.json.
        # Patch Path.home() so this test writes to a throwaway temp dir instead.
        with patch("pathlib.Path.home", return_value=tmp_path):
            c = _client()
            r = c.post("/api/memories", json={"text": "Test memory #api"})
        assert r.status_code == 201
        data = r.json()
        assert "memory" in data
        assert "Test memory" in data["memory"]["text"]

    def test_created_memory_appears_in_list(self, tmp_path):
        with patch("pathlib.Path.home", return_value=tmp_path):
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
        mock_daemon.return_value.start.return_value = {"started": True, "pid": 12345, "log": "/tmp/d.log"}
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


@contextmanager
def _isolated_service(tmp_path):
    """Patch service.py's module-level repos onto tmp_path-backed instances.

    api/router.py's flow endpoints all go through service.py's singletons
    (service._flow_repo, service._doc_repo) rather than instantiating their
    own repo per call, so patching those two is enough to isolate a test
    run from the real data/flowcore.db.
    """
    import service
    from storage import DocumentRepository, FlowRepository

    with (
        patch.object(service, "_flow_repo", FlowRepository(db_path=str(tmp_path / "flows.db"))),
        patch.object(service, "_doc_repo", DocumentRepository(db_path=str(tmp_path / "docs.db"))),
    ):
        yield


class TestFlowsEndpoints:
    def test_create_list_run_delete_flow(self, tmp_path):
        with _isolated_service(tmp_path):
            c = _client()

            r = c.post(
                "/api/flows",
                json={"name": "Test Flow", "steps": [{"action": "note", "params": {"text": "hi"}}]},
            )
            assert r.status_code == 201
            flow_id = r.json()["id"]

            r = c.get("/api/flows")
            assert r.status_code == 200
            assert any(f["id"] == flow_id for f in r.json()["flows"])

            r = c.get(f"/api/flows/{flow_id}")
            assert r.status_code == 200
            assert r.json()["name"] == "Test Flow"

            r = c.post(f"/api/flows/{flow_id}/run")
            assert r.status_code == 200
            execution = r.json()
            # The bug this whole feature exists to fix: the old (Sprint
            # 14-removed) stub never set these.
            assert execution["status"] == "completed"
            assert execution["started_at"] is not None
            assert execution["finished_at"] is not None
            assert execution["step_results"][0]["status"] == "completed"

            r = c.get("/api/executions", params={"flow_id": flow_id})
            assert r.status_code == 200
            assert len(r.json()["executions"]) == 1

            r = c.get(f"/api/executions/{execution['id']}")
            assert r.status_code == 200

            r = c.delete(f"/api/flows/{flow_id}")
            assert r.status_code == 200
            assert r.json()["deleted"] is True

    def test_create_flow_unknown_action_returns_422(self, tmp_path):
        with _isolated_service(tmp_path):
            r = _client().post("/api/flows", json={"name": "Bad", "steps": [{"action": "nonexistent"}]})
            assert r.status_code == 422

    def test_get_missing_flow_returns_404(self, tmp_path):
        with _isolated_service(tmp_path):
            r = _client().get("/api/flows/999999")
            assert r.status_code == 404

    def test_run_missing_flow_returns_404(self, tmp_path):
        with _isolated_service(tmp_path):
            r = _client().post("/api/flows/999999/run")
            assert r.status_code == 404

    def test_delete_missing_flow_returns_404(self, tmp_path):
        with _isolated_service(tmp_path):
            r = _client().delete("/api/flows/999999")
            assert r.status_code == 404

    def test_get_missing_execution_returns_404(self, tmp_path):
        with _isolated_service(tmp_path):
            r = _client().get("/api/executions/999999")
            assert r.status_code == 404
