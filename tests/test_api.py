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
    # /api/notify routes through service.send_notification -> the capability
    # registry (Sprint 17, Milestone 1) — mocked at that single choke point
    # rather than the old direct termux-notification shell call.
    def test_notify_without_termux_api(self):
        from capability.adapters.base import CapabilityResult

        c = _client()
        with patch("service._registry.call", return_value=CapabilityResult.fail("not installed", "test")):
            r = c.post("/api/notify", json={"title": "Test", "body": "Hello"})
        assert r.status_code == 200
        assert r.json()["sent"] is False

    def test_notify_with_termux_api(self):
        from capability.adapters.base import CapabilityResult

        c = _client()
        with patch("service._registry.call", return_value=CapabilityResult.ok({"sent": True}, "test")) as m:
            r = c.post("/api/notify", json={"title": "FlowCore", "body": "Test notification"})
        assert r.status_code == 200
        assert r.json()["sent"] is True
        m.assert_called_once_with("sendNotification", "FlowCore", "Test notification")


class TestSystemEndpoint:
    # /api/system now routes battery/storage/wifi/android_version through the
    # capability layer (Sprint 17, Milestone 1) instead of ad hoc shell calls.
    # These tests confirm the response still has the same keys/shape the Web
    # UI's renderSys() depends on — a regression check, not a new contract.
    def test_returns_200_with_no_capabilities_available(self):
        from capability.adapters.base import CapabilityResult

        c = _client()
        with patch("service._registry.call", return_value=CapabilityResult.fail("n/a", "test")):
            r = c.get("/api/system")
        assert r.status_code == 200
        data = r.json()
        assert "uptime_api" in data
        assert "battery" not in data  # omitted, not crashed, when unavailable

    def test_battery_shape_matches_web_ui_contract(self):
        from capability.adapters.base import CapabilityResult

        def fake_call(capability, *args):
            if capability == "getBattery":
                return CapabilityResult.ok(
                    {"level": 87, "status": "charging", "health": "good", "temperature": 30, "plugged": "AC"}, "test"
                )
            return CapabilityResult.fail("n/a", "test")

        c = _client()
        with patch("service._registry.call", side_effect=fake_call):
            r = c.get("/api/system")
        battery = r.json()["battery"]
        assert battery["percentage"] == 87
        assert battery["status"] == "charging"
        assert battery["health"] == "good"

    def test_storage_and_wifi_included_when_available(self):
        from capability.adapters.base import CapabilityResult

        def fake_call(capability, *args):
            if capability == "getDiskUsage":
                return CapabilityResult.ok({"total": "10G", "used": "3G", "avail": "7G"}, "test")
            if capability == "getNetworkInfo":
                return CapabilityResult.ok({"ssid": "MyWifi", "rssi": -50}, "test")
            return CapabilityResult.fail("n/a", "test")

        c = _client()
        with patch("service._registry.call", side_effect=fake_call):
            r = c.get("/api/system")
        data = r.json()
        assert data["storage"]["total"] == "10G"
        assert data["wifi"]["ssid"] == "MyWifi"


class TestClipboardEndpoint:
    def test_get_clipboard_unavailable_returns_503(self):
        from capability.adapters.base import CapabilityResult

        c = _client()
        with patch("service._registry.call", return_value=CapabilityResult.fail("n/a", "test")):
            r = c.get("/api/clipboard")
        assert r.status_code == 503

    def test_get_clipboard_success(self):
        from capability.adapters.base import CapabilityResult

        c = _client()
        with patch("service._registry.call", return_value=CapabilityResult.ok({"text": "hello"}, "test")):
            r = c.get("/api/clipboard")
        assert r.status_code == 200
        assert r.json()["text"] == "hello"

    def test_set_clipboard_passes_text(self):
        from capability.adapters.base import CapabilityResult

        c = _client()
        with patch("service._registry.call", return_value=CapabilityResult.ok({"set": True}, "test")) as m:
            r = c.post("/api/clipboard", json={"text": "copied text"})
        assert r.status_code == 200
        m.assert_called_once_with("setClipboard", "copied text")


class TestAppsEndpoint:
    def test_list_apps_unavailable_returns_503(self):
        from capability.adapters.base import CapabilityResult

        c = _client()
        with patch("service._registry.call", return_value=CapabilityResult.fail("n/a", "test")):
            r = c.get("/api/apps")
        assert r.status_code == 503

    def test_list_apps_success(self):
        from capability.adapters.base import CapabilityResult

        c = _client()
        data = {"count": 2, "packages": ["com.a", "com.b"]}
        with patch("service._registry.call", return_value=CapabilityResult.ok(data, "test")):
            r = c.get("/api/apps")
        assert r.status_code == 200
        assert r.json()["count"] == 2


class TestOutlookEndpoints:
    # service.outlook_* is mocked directly — no real network/Azure AD
    # credentials needed (see tests/test_outlook.py for runtime.outlook's
    # own coverage against mocked msal/requests).
    def test_auth_start_not_configured_returns_503(self):
        from runtime.outlook import OutlookNotConfiguredError

        c = _client()
        with patch("service.outlook_auth_start", side_effect=OutlookNotConfiguredError("no client id")):
            r = c.post("/api/outlook/auth/start")
        assert r.status_code == 503

    def test_auth_start_success(self):
        c = _client()
        data = {"user_code": "ABC123", "verification_uri": "https://microsoft.com/devicelogin", "expires_in": 900}
        with patch("service.outlook_auth_start", return_value=data):
            r = c.post("/api/outlook/auth/start")
        assert r.status_code == 200
        assert r.json()["user_code"] == "ABC123"

    def test_auth_status(self):
        c = _client()
        with patch("service.outlook_auth_status", return_value={"status": "idle", "authenticated": False}):
            r = c.get("/api/outlook/auth/status")
        assert r.status_code == 200
        assert r.json()["authenticated"] is False

    def test_messages_not_configured_returns_503(self):
        from runtime.outlook import OutlookNotConfiguredError

        c = _client()
        with patch("service.outlook_messages", side_effect=OutlookNotConfiguredError("no client id")):
            r = c.get("/api/outlook/messages")
        assert r.status_code == 503

    def test_messages_auth_required_returns_401(self):
        from runtime.outlook import OutlookAuthRequiredError

        c = _client()
        with patch("service.outlook_messages", side_effect=OutlookAuthRequiredError("not authed")):
            r = c.get("/api/outlook/messages")
        assert r.status_code == 401

    def test_messages_success(self):
        c = _client()
        msgs = [{"subject": "Hi", "from": "a@b.com", "received": "2026-08-05T00:00:00Z", "is_read": False}]
        with patch("service.outlook_messages", return_value=msgs):
            r = c.get("/api/outlook/messages", params={"limit": 5})
        assert r.status_code == 200
        assert r.json()["messages"] == msgs

    def test_unread_success(self):
        c = _client()
        with patch("service.outlook_unread_count", return_value=3):
            r = c.get("/api/outlook/unread")
        assert r.status_code == 200
        assert r.json()["unread"] == 3

    def test_search_requires_query_param(self):
        c = _client()
        r = c.get("/api/outlook/search")
        assert r.status_code == 422

    def test_search_success(self):
        c = _client()
        with patch("service.outlook_search", return_value=[]) as m:
            r = c.get("/api/outlook/search", params={"q": "invoice"})
        assert r.status_code == 200
        m.assert_called_once_with("invoice", 10)


class TestCalendarEndpoints:
    # service.calendar_* is mocked directly — no real network/Azure AD
    # credentials needed (see tests/test_calendar.py for runtime.calendar's
    # own coverage against mocked graph_get).
    def test_today_not_configured_returns_503(self):
        from runtime.calendar import CalendarNotConfiguredError

        c = _client()
        with patch("service.calendar_today", side_effect=CalendarNotConfiguredError("no client id")):
            r = c.get("/api/calendar/today")
        assert r.status_code == 503

    def test_today_auth_required_returns_401(self):
        from runtime.calendar import CalendarAuthRequiredError

        c = _client()
        with patch("service.calendar_today", side_effect=CalendarAuthRequiredError("not authed")):
            r = c.get("/api/calendar/today")
        assert r.status_code == 401

    def test_today_success(self):
        c = _client()
        events = [{"id": "e1", "subject": "Standup", "start": "...", "end": "..."}]
        with patch("service.calendar_today", return_value=events):
            r = c.get("/api/calendar/today")
        assert r.status_code == 200
        assert r.json()["events"] == events

    def test_tomorrow_success(self):
        c = _client()
        with patch("service.calendar_tomorrow", return_value=[]):
            r = c.get("/api/calendar/tomorrow")
        assert r.status_code == 200

    def test_week_success(self):
        c = _client()
        with patch("service.calendar_week", return_value=[]):
            r = c.get("/api/calendar/week")
        assert r.status_code == 200

    def test_next_success(self):
        c = _client()
        with patch("service.calendar_next", return_value=None):
            r = c.get("/api/calendar/next")
        assert r.status_code == 200
        assert r.json()["event"] is None

    def test_search_requires_query_param(self):
        c = _client()
        r = c.get("/api/calendar/search")
        assert r.status_code == 422

    def test_search_success(self):
        c = _client()
        with patch("service.calendar_search", return_value=[]) as m:
            r = c.get("/api/calendar/search", params={"q": "budget"})
        assert r.status_code == 200
        m.assert_called_once_with("budget", 10)


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

    def test_list_executions_limit_param(self, tmp_path):
        with _isolated_service(tmp_path):
            c = _client()
            flow_id = c.post("/api/flows", json={"name": "Limit Test", "steps": []}).json()["id"]
            for _ in range(4):
                c.post(f"/api/flows/{flow_id}/run")

            r = c.get("/api/executions", params={"limit": 2})
            assert r.status_code == 200
            assert len(r.json()["executions"]) == 2

    def test_list_executions_limit_over_500_rejected(self, tmp_path):
        with _isolated_service(tmp_path):
            r = _client().get("/api/executions", params={"limit": 501})
            assert r.status_code == 422
