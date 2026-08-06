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

    def test_create_requires_fields(self):
        c = _client()
        r = c.post("/api/calendar", json={"subject": "Missing start/end"})
        assert r.status_code == 422

    def test_create_success(self):
        c = _client()
        event = {"id": "e1", "subject": "Standup"}
        with patch("service.calendar_create", return_value=event) as m:
            r = c.post(
                "/api/calendar",
                json={"subject": "Standup", "start": "2026-08-10T10:00:00", "end": "2026-08-10T10:30:00"},
            )
        assert r.status_code == 201
        assert r.json() == event
        m.assert_called_once_with("Standup", "2026-08-10T10:00:00", "2026-08-10T10:30:00", "UTC", "", "", [])

    def test_create_not_configured_returns_503(self):
        from runtime.calendar import CalendarNotConfiguredError

        c = _client()
        with patch("service.calendar_create", side_effect=CalendarNotConfiguredError("no client id")):
            r = c.post(
                "/api/calendar",
                json={"subject": "X", "start": "2026-08-10T10:00:00", "end": "2026-08-10T10:30:00"},
            )
        assert r.status_code == 503

    def test_update_no_fields_returns_422(self):
        c = _client()
        r = c.put("/api/calendar/e1", json={})
        assert r.status_code == 422

    def test_update_success(self):
        c = _client()
        with patch("service.calendar_update", return_value={"id": "e1", "subject": "Renamed"}) as m:
            r = c.put("/api/calendar/e1", json={"subject": "Renamed"})
        assert r.status_code == 200
        assert r.json()["subject"] == "Renamed"
        m.assert_called_once_with("e1", subject="Renamed")

    def test_update_maps_timezone_field_when_start_or_end_given(self):
        c = _client()
        with patch("service.calendar_update", return_value={}) as m:
            r = c.put("/api/calendar/e1", json={"start": "2026-08-11T09:00:00", "timezone": "America/Sao_Paulo"})
        assert r.status_code == 200
        m.assert_called_once_with("e1", start="2026-08-11T09:00:00", timezone_="America/Sao_Paulo")

    def test_delete_success(self):
        c = _client()
        with patch("service.calendar_delete", return_value=None) as m:
            r = c.delete("/api/calendar/e1")
        assert r.status_code == 200
        assert r.json()["deleted"] is True
        m.assert_called_once_with("e1")

    def test_delete_not_configured_returns_503(self):
        from runtime.calendar import CalendarNotConfiguredError

        c = _client()
        with patch("service.calendar_delete", side_effect=CalendarNotConfiguredError("no client id")):
            r = c.delete("/api/calendar/e1")
        assert r.status_code == 503


class TestWhatsAppEndpoints:
    # service.whatsapp_* is mocked directly — no real Evolution API calls
    # (see tests/test_whatsapp.py for runtime.whatsapp's own coverage
    # against mocked requests).
    def test_health_success(self):
        c = _client()
        payload = {"status": 200, "message": "Welcome", "version": "2.2.3"}
        with patch("service.whatsapp_health", return_value=payload):
            r = c.get("/api/whatsapp/health")
        assert r.status_code == 200
        assert r.json() == payload

    def test_health_unreachable_returns_502(self):
        from runtime.whatsapp import WhatsAppError

        c = _client()
        with patch("service.whatsapp_health", side_effect=WhatsAppError("unreachable")):
            r = c.get("/api/whatsapp/health")
        assert r.status_code == 502

    def test_status_not_configured_returns_503(self):
        from runtime.whatsapp import WhatsAppNotConfiguredError

        c = _client()
        with patch("service.whatsapp_status", side_effect=WhatsAppNotConfiguredError("no key")):
            r = c.get("/api/whatsapp/status")
        assert r.status_code == 503

    def test_status_success(self):
        c = _client()
        payload = {"instance": {"state": "open"}}
        with patch("service.whatsapp_status", return_value=payload):
            r = c.get("/api/whatsapp/status")
        assert r.status_code == 200
        assert r.json() == payload

    def test_send_not_configured_returns_503(self):
        from runtime.whatsapp import WhatsAppNotConfiguredError

        c = _client()
        with patch("service.whatsapp_send", side_effect=WhatsAppNotConfiguredError("no key")):
            r = c.post("/api/whatsapp/send", json={"number": "5511999999999", "text": "hi"})
        assert r.status_code == 503

    def test_send_success(self):
        c = _client()
        with patch("service.whatsapp_send", return_value={"status": "PENDING"}) as m:
            r = c.post("/api/whatsapp/send", json={"number": "5511999999999", "text": "hi"})
        assert r.status_code == 200
        m.assert_called_once_with("5511999999999", "hi")

    def test_send_requires_fields(self):
        c = _client()
        r = c.post("/api/whatsapp/send", json={"number": "5511999999999"})
        assert r.status_code == 422


class TestTelegramEndpoints:
    # service.telegram_* is mocked directly — no real Telegram API calls
    # (see tests/test_telegram.py for runtime.telegram's own coverage
    # against mocked urllib).
    def test_health_success(self):
        c = _client()
        payload = {"id": 123, "username": "spcx_monitor_bot"}
        with patch("service.telegram_health", return_value=payload):
            r = c.get("/api/telegram/health")
        assert r.status_code == 200
        assert r.json() == payload

    def test_health_not_configured_returns_503(self):
        from runtime.telegram import TelegramNotConfiguredError

        c = _client()
        with patch("service.telegram_health", side_effect=TelegramNotConfiguredError("no token")):
            r = c.get("/api/telegram/health")
        assert r.status_code == 503

    def test_health_unreachable_returns_502(self):
        from runtime.telegram import TelegramError

        c = _client()
        with patch("service.telegram_health", side_effect=TelegramError("unreachable")):
            r = c.get("/api/telegram/health")
        assert r.status_code == 502

    def test_config_success(self):
        c = _client()
        payload = {"configured": False, "token_set": False, "chat_id_set": False}
        with patch("service.telegram_configuration", return_value=payload):
            r = c.get("/api/telegram/config")
        assert r.status_code == 200
        assert r.json() == payload

    def test_send_not_configured_returns_503(self):
        from runtime.telegram import TelegramNotConfiguredError

        c = _client()
        with patch("service.telegram_send", side_effect=TelegramNotConfiguredError("no token")):
            r = c.post("/api/telegram/send", json={"text": "hi"})
        assert r.status_code == 503

    def test_send_success(self):
        c = _client()
        with patch("service.telegram_send", return_value={"message_id": 1}) as m:
            r = c.post("/api/telegram/send", json={"text": "hi", "chat_id": "999"})
        assert r.status_code == 200
        m.assert_called_once_with("hi", "999")

    def test_send_without_chat_id_defaults_to_none(self):
        c = _client()
        with patch("service.telegram_send", return_value={"message_id": 1}) as m:
            r = c.post("/api/telegram/send", json={"text": "hi"})
        assert r.status_code == 200
        m.assert_called_once_with("hi", None)

    def test_send_requires_text(self):
        c = _client()
        r = c.post("/api/telegram/send", json={})
        assert r.status_code == 422


class TestObserverEndpoints:
    # service.observer_* is mocked directly — no real yfinance/network calls
    # (see tests/observers/ for the runtime.observers framework's own
    # coverage, mocked at the yfinance boundary).
    def test_registry_success(self):
        c = _client()
        payload = [{"source": "vix", "category": "volatility", "symbol": "^VIX"}]
        with patch("service.observer_registry_info", return_value=payload):
            r = c.get("/api/observer/registry")
        assert r.status_code == 200
        assert r.json() == {"observers": payload}

    def test_events_success(self):
        c = _client()
        payload = [
            {
                "id": "abc",
                "timestamp": "t",
                "source": "vix",
                "category": "volatility",
                "symbol": "^VIX",
                "event": "initial_observation",
                "severity": "info",
                "confidence": 0.95,
                "payload": {"value": 15.81, "previous_close": 16.5},
                "metadata": {"provider": "yfinance"},
            }
        ]
        with patch("service.observer_events", return_value=payload):
            r = c.get("/api/observer/events")
        assert r.status_code == 200
        assert r.json() == {"events": payload}

    def test_health_success(self):
        c = _client()
        payload = {
            "id": "abc",
            "timestamp": "t",
            "source": "vix",
            "category": "volatility",
            "symbol": "^VIX",
            "event": "initial_observation",
            "severity": "info",
            "confidence": 0.95,
            "payload": {"value": 15.81, "previous_close": 16.5},
            "metadata": {"provider": "yfinance"},
        }
        with patch("service.observer_health", return_value=payload):
            r = c.get("/api/observer/health")
        assert r.status_code == 200
        assert r.json() == payload

    def test_health_failure_returns_502(self):
        from runtime.observers.base import ObserverError

        c = _client()
        with patch("service.observer_health", side_effect=ObserverError("timeout")):
            r = c.get("/api/observer/health")
        assert r.status_code == 502

    def test_source_events_success(self):
        c = _client()
        payload = [
            {
                "id": "abc",
                "timestamp": "t",
                "source": "gold",
                "category": "commodities",
                "symbol": "GC=F",
                "event": "initial_observation",
                "severity": "info",
                "confidence": 0.95,
                "payload": {"value": 4305.0, "previous_close": 4186.6},
                "metadata": {"provider": "yfinance"},
            }
        ]
        with (
            patch("runtime.observers.registry.registry.names", return_value=["gold"]),
            patch("service.observer_source_events", return_value=payload),
        ):
            r = c.get("/api/observer/events/gold")
        assert r.status_code == 200
        assert r.json() == {"events": payload}

    def test_unknown_source_returns_404(self):
        c = _client()
        r = c.get("/api/observer/events/bogus")
        assert r.status_code == 404

    def test_source_events_failure_returns_502(self):
        from runtime.observers.base import ObserverError

        c = _client()
        with patch("service.observer_source_events", side_effect=ObserverError("fetch failed")):
            r = c.get("/api/observer/events/vix")
        assert r.status_code == 502


class TestMacroScoreEndpoints:
    # service.macro_score_* is mocked directly — no real storage/computation
    # (see tests/macro_score/ for MacroScoreEngine's own coverage against a
    # real tmp_path-backed EventRepository).
    def test_dimensions_success(self):
        c = _client()
        payload = {"commodities": ["oil", "gold"], "liquidity": ["treasury", "dollar"], "risk_sentiment": ["vix"]}
        with patch("service.macro_score_dimensions", return_value=payload):
            r = c.get("/api/macro-score/dimensions")
        assert r.status_code == 200
        assert r.json() == {"dimensions": payload}

    def test_scores_success(self):
        c = _client()
        payload = [
            {
                "dimension": "risk_sentiment",
                "status": "insufficient_data",
                "score": None,
                "window_days": 30,
                "z_scores": {},
                "sample_counts": {"vix": 0},
                "computed_at": "t",
            }
        ]
        with patch("service.macro_score_compute_all", return_value=payload):
            r = c.get("/api/macro-score/scores")
        assert r.status_code == 200
        assert r.json() == {"scores": payload}

    def test_single_dimension_success(self):
        c = _client()
        payload = {
            "dimension": "risk_sentiment",
            "status": "scored",
            "score": 1.23,
            "window_days": 30,
            "z_scores": {"vix": 1.23},
            "sample_counts": {"vix": 6},
            "computed_at": "t",
        }
        with patch("service.macro_score_compute", return_value=payload):
            r = c.get("/api/macro-score/scores/risk_sentiment")
        assert r.status_code == 200
        assert r.json() == payload

    def test_unknown_dimension_returns_404(self):
        c = _client()
        r = c.get("/api/macro-score/scores/bogus")
        assert r.status_code == 404


class TestRegimeEndpoints:
    # service.regime_* is mocked directly — no real storage/computation
    # (see tests/regime/ for RegimeEngine's own coverage against a real
    # tmp_path-backed EventRepository/MacroScoreEngine).
    def test_signals_success(self):
        c = _client()
        payload = [
            {
                "dimension": "risk_sentiment",
                "regime": "insufficient_data",
                "score": None,
                "threshold": 1.0,
                "computed_at": "t",
            }
        ]
        with patch("service.regime_classify_all", return_value=payload):
            r = c.get("/api/regime/signals")
        assert r.status_code == 200
        assert r.json() == {"signals": payload}

    def test_single_dimension_success(self):
        c = _client()
        payload = {
            "dimension": "risk_sentiment",
            "regime": "elevated",
            "score": 2.05,
            "threshold": 1.0,
            "computed_at": "t",
        }
        with patch("service.regime_classify", return_value=payload):
            r = c.get("/api/regime/signals/risk_sentiment")
        assert r.status_code == 200
        assert r.json() == payload

    def test_unknown_dimension_returns_404(self):
        c = _client()
        r = c.get("/api/regime/signals/bogus")
        assert r.status_code == 404


class TestPortfolioEndpoints:
    # service.* is mocked directly — no real storage/yfinance calls (see
    # tests/test_portfolio_repo.py and tests/portfolio/ for the repository
    # and runtime layers' own coverage).
    def test_create_portfolio(self):
        c = _client()
        payload = {"id": 1, "name": "Corretora XP", "created_at": "t"}
        with patch("service.create_portfolio", return_value=payload):
            r = c.post("/api/portfolios", json={"name": "Corretora XP"})
        assert r.status_code == 201
        assert r.json() == payload

    def test_list_portfolios(self):
        c = _client()
        payload = [{"id": 1, "name": "X", "created_at": "t"}]
        with patch("service.list_portfolios", return_value=payload):
            r = c.get("/api/portfolios")
        assert r.status_code == 200
        assert r.json() == {"portfolios": payload}

    def test_get_portfolio_success(self):
        c = _client()
        payload = {"id": 1, "name": "X", "created_at": "t"}
        with patch("service.get_portfolio", return_value=payload):
            r = c.get("/api/portfolios/1")
        assert r.status_code == 200
        assert r.json() == payload

    def test_get_portfolio_missing_returns_404(self):
        c = _client()
        with patch("service.get_portfolio", side_effect=ValueError("Portfolio not found: 999")):
            r = c.get("/api/portfolios/999")
        assert r.status_code == 404

    def test_delete_portfolio_success(self):
        c = _client()
        with patch("service.delete_portfolio", return_value=True):
            r = c.delete("/api/portfolios/1")
        assert r.status_code == 200
        assert r.json() == {"deleted": True}

    def test_delete_portfolio_missing_returns_404(self):
        c = _client()
        with patch("service.delete_portfolio", return_value=False):
            r = c.delete("/api/portfolios/999")
        assert r.status_code == 404

    def test_summary_success(self):
        c = _client()
        payload = {
            "portfolio_id": 1,
            "holding_count": 1,
            "valued_holding_count": 1,
            "total_market_value": 100.0,
            "total_cost_basis": 90.0,
            "total_unrealized_gain": 10.0,
            "total_unrealized_gain_pct": 11.11,
        }
        with patch("service.portfolio_summary", return_value=payload):
            r = c.get("/api/portfolios/1/summary")
        assert r.status_code == 200
        assert r.json() == payload

    def test_summary_missing_portfolio_returns_404(self):
        c = _client()
        with patch("service.portfolio_summary", side_effect=ValueError("Portfolio not found: 999")):
            r = c.get("/api/portfolios/999/summary")
        assert r.status_code == 404

    def test_add_holding_success(self):
        c = _client()
        payload = {"id": 1, "portfolio_id": 1, "symbol": "AAPL", "quantity": 10.0, "average_cost": 150.0}
        with patch("service.add_holding", return_value=payload) as m:
            r = c.post("/api/portfolios/1/holdings", json={"symbol": "AAPL", "quantity": 10, "average_cost": 150.0})
        assert r.status_code == 201
        assert r.json() == payload
        m.assert_called_once_with(1, "AAPL", 10.0, 150.0, "USD")

    def test_add_holding_missing_portfolio_returns_404(self):
        c = _client()
        with patch("service.add_holding", side_effect=ValueError("Portfolio not found: 999")):
            r = c.post("/api/portfolios/999/holdings", json={"symbol": "AAPL", "quantity": 1, "average_cost": 1.0})
        assert r.status_code == 404

    def test_list_holdings_success(self):
        c = _client()
        payload = [{"id": 1, "symbol": "AAPL", "market_value": 100.0}]
        with patch("service.list_holdings", return_value=payload):
            r = c.get("/api/portfolios/1/holdings")
        assert r.status_code == 200
        assert r.json() == {"holdings": payload}

    def test_list_holdings_missing_portfolio_returns_404(self):
        c = _client()
        with patch("service.list_holdings", side_effect=ValueError("Portfolio not found: 999")):
            r = c.get("/api/portfolios/999/holdings")
        assert r.status_code == 404

    def test_update_holding_success(self):
        c = _client()
        payload = {"id": 1, "symbol": "AAPL", "quantity": 20.0}
        with patch("service.update_holding", return_value=payload):
            r = c.put("/api/holdings/1", json={"quantity": 20})
        assert r.status_code == 200
        assert r.json() == payload

    def test_update_holding_missing_returns_404(self):
        c = _client()
        with patch("service.update_holding", side_effect=ValueError("Holding not found: 999")):
            r = c.put("/api/holdings/999", json={"quantity": 20})
        assert r.status_code == 404

    def test_delete_holding_success(self):
        c = _client()
        with patch("service.delete_holding", return_value=True):
            r = c.delete("/api/holdings/1")
        assert r.status_code == 200
        assert r.json() == {"deleted": True}

    def test_delete_holding_missing_returns_404(self):
        c = _client()
        with patch("service.delete_holding", return_value=False):
            r = c.delete("/api/holdings/999")
        assert r.status_code == 404


class TestExposureEndpoints:
    # service.* is mocked directly — ExposureEngine's own math is covered
    # by tests/exposure/test_engine.py.
    def test_full_report_success(self):
        c = _client()
        payload = {"sector": {"dimension": "sector", "buckets": []}}
        with patch("service.portfolio_exposure", return_value=payload) as m:
            r = c.get("/api/portfolios/1/exposure")
        assert r.status_code == 200
        assert r.json() == payload
        m.assert_called_once_with(1)

    def test_full_report_missing_portfolio_returns_404(self):
        c = _client()
        with patch("service.portfolio_exposure", side_effect=ValueError("Portfolio not found: 999")):
            r = c.get("/api/portfolios/999/exposure")
        assert r.status_code == 404

    def test_single_dimension_success(self):
        c = _client()
        payload = {"dimension": "sector", "buckets": []}
        with patch("service.portfolio_exposure", return_value=payload) as m:
            r = c.get("/api/portfolios/1/exposure/sector")
        assert r.status_code == 200
        assert r.json() == payload
        m.assert_called_once_with(1, "sector")

    def test_single_dimension_missing_portfolio_returns_404(self):
        c = _client()
        with patch("service.portfolio_exposure", side_effect=ValueError("Portfolio not found: 999")):
            r = c.get("/api/portfolios/999/exposure/sector")
        assert r.status_code == 404

    def test_single_dimension_unknown_returns_404(self):
        from runtime.exposure import ExposureError

        c = _client()
        with patch("service.portfolio_exposure", side_effect=ExposureError("Unknown exposure dimension: 'bogus'")):
            r = c.get("/api/portfolios/1/exposure/bogus")
        assert r.status_code == 404

    def test_concentration_success(self):
        c = _client()
        payload = {"hhi": 5331.7, "top_holding_weight_pct": 62.9}
        with patch("service.portfolio_concentration", return_value=payload):
            r = c.get("/api/portfolios/1/concentration")
        assert r.status_code == 200
        assert r.json() == payload

    def test_concentration_missing_portfolio_returns_404(self):
        c = _client()
        with patch("service.portfolio_concentration", side_effect=ValueError("Portfolio not found: 999")):
            r = c.get("/api/portfolios/999/concentration")
        assert r.status_code == 404


class TestImpactEndpoints:
    # service.* is mocked directly — ImpactEngine's own logic is covered
    # by tests/impact/.
    def test_impact_success(self):
        c = _client()
        payload = {"portfolio_id": 1, "overall_impact": "negative", "drivers": []}
        with patch("service.portfolio_impact", return_value=payload) as m:
            r = c.get("/api/portfolios/1/impact")
        assert r.status_code == 200
        assert r.json() == payload
        m.assert_called_once_with(1)

    def test_impact_missing_portfolio_returns_404(self):
        c = _client()
        with patch("service.portfolio_impact", side_effect=ValueError("Portfolio not found: 999")):
            r = c.get("/api/portfolios/999/impact")
        assert r.status_code == 404

    def test_recommendations_success_default_shelf(self):
        c = _client()
        payload = {"portfolio_id": 1, "shelf": "us_etf", "recommendations": [], "opportunities": []}
        with patch("service.portfolio_recommendations", return_value=payload) as m:
            r = c.get("/api/portfolios/1/recommendations")
        assert r.status_code == 200
        assert r.json() == payload
        m.assert_called_once_with(1, "us_etf")

    def test_recommendations_honors_shelf_query_param(self):
        c = _client()
        payload = {"portfolio_id": 1, "shelf": "br_renda_fixa", "recommendations": [], "opportunities": []}
        with patch("service.portfolio_recommendations", return_value=payload) as m:
            r = c.get("/api/portfolios/1/recommendations?shelf=br_renda_fixa")
        assert r.status_code == 200
        m.assert_called_once_with(1, "br_renda_fixa")

    def test_recommendations_missing_portfolio_returns_404(self):
        c = _client()
        with patch("service.portfolio_recommendations", side_effect=ValueError("Portfolio not found: 999")):
            r = c.get("/api/portfolios/999/recommendations")
        assert r.status_code == 404

    def test_recommendations_unknown_shelf_returns_404(self):
        from runtime.product_mapping import ProductMappingError

        c = _client()
        with patch("service.portfolio_recommendations", side_effect=ProductMappingError("Unknown product shelf: 'x'")):
            r = c.get("/api/portfolios/1/recommendations?shelf=x")
        assert r.status_code == 404

    def test_product_shelves_endpoint(self):
        c = _client()
        with patch("service.product_shelves", return_value=["us_etf", "br_renda_fixa"]):
            r = c.get("/api/product-shelves")
        assert r.status_code == 200
        assert r.json() == {"shelves": ["us_etf", "br_renda_fixa"]}


class TestDecisionEndpoints:
    # service.* is mocked directly — DecisionEngine's own logic is
    # covered by tests/decision/.
    def test_decision_success_default_shelf(self):
        c = _client()
        payload = {"portfolio_id": 1, "overall_priority": "HIGH", "decisions": []}
        with patch("service.portfolio_decision", return_value=payload) as m:
            r = c.get("/api/portfolios/1/decision")
        assert r.status_code == 200
        assert r.json() == payload
        m.assert_called_once_with(1, "us_etf")

    def test_decision_honors_shelf_query_param(self):
        c = _client()
        payload = {"portfolio_id": 1, "overall_priority": "LOW", "decisions": []}
        with patch("service.portfolio_decision", return_value=payload) as m:
            r = c.get("/api/portfolios/1/decision?shelf=br_renda_fixa")
        assert r.status_code == 200
        m.assert_called_once_with(1, "br_renda_fixa")

    def test_decision_missing_portfolio_returns_404(self):
        c = _client()
        with patch("service.portfolio_decision", side_effect=ValueError("Portfolio not found: 999")):
            r = c.get("/api/portfolios/999/decision")
        assert r.status_code == 404

    def test_decision_unknown_shelf_returns_404(self):
        from runtime.product_mapping import ProductMappingError

        c = _client()
        with patch("service.portfolio_decision", side_effect=ProductMappingError("Unknown product shelf: 'x'")):
            r = c.get("/api/portfolios/1/decision?shelf=x")
        assert r.status_code == 404

    def test_decision_queue_success(self):
        c = _client()
        with patch("service.portfolio_decision_queue", return_value=[{"id": "reduce_duration"}]) as m:
            r = c.get("/api/portfolios/1/decision/queue")
        assert r.status_code == 200
        assert r.json() == {"decisions": [{"id": "reduce_duration"}]}
        m.assert_called_once_with(1, "us_etf")

    def test_decision_queue_missing_portfolio_returns_404(self):
        c = _client()
        with patch("service.portfolio_decision_queue", side_effect=ValueError("Portfolio not found: 999")):
            r = c.get("/api/portfolios/999/decision/queue")
        assert r.status_code == 404

    def test_decision_score_success(self):
        c = _client()
        payload = {"overall": 60.0, "overall_status": "computed", "sub_scores": []}
        with patch("service.portfolio_score", return_value=payload) as m:
            r = c.get("/api/portfolios/1/decision/score")
        assert r.status_code == 200
        assert r.json() == payload
        m.assert_called_once_with(1)

    def test_decision_score_missing_portfolio_returns_404(self):
        c = _client()
        with patch("service.portfolio_score", side_effect=ValueError("Portfolio not found: 999")):
            r = c.get("/api/portfolios/999/decision/score")
        assert r.status_code == 404

    def test_reason_chain_all_decisions(self):
        c = _client()
        payload = {"portfolio_id": 1, "reason_chains": {"reduce_duration": ["step1", "step2"]}}
        with patch("service.portfolio_reason_chain", return_value=payload) as m:
            r = c.get("/api/portfolios/1/reason-chain")
        assert r.status_code == 200
        assert r.json() == payload
        m.assert_called_once_with(1, "", "us_etf")

    def test_reason_chain_single_decision(self):
        c = _client()
        payload = {"portfolio_id": 1, "decision_id": "reduce_duration", "reason_chain": ["step1"]}
        with patch("service.portfolio_reason_chain", return_value=payload) as m:
            r = c.get("/api/portfolios/1/reason-chain?decision=reduce_duration")
        assert r.status_code == 200
        assert r.json() == payload
        m.assert_called_once_with(1, "reduce_duration", "us_etf")

    def test_reason_chain_unknown_decision_returns_404(self):
        c = _client()
        with patch("service.portfolio_reason_chain", side_effect=ValueError("Decision not found: 'bogus'")):
            r = c.get("/api/portfolios/1/reason-chain?decision=bogus")
        assert r.status_code == 404

    def test_reason_chain_missing_portfolio_returns_404(self):
        c = _client()
        with patch("service.portfolio_reason_chain", side_effect=ValueError("Portfolio not found: 999")):
            r = c.get("/api/portfolios/999/reason-chain")
        assert r.status_code == 404


class TestNarrativeEndpoints:
    # service.* is mocked directly — NarrativeEngine's own logic is
    # covered by tests/narrative/.
    def test_narrative_success_default_shelf(self):
        c = _client()
        payload = {
            "portfolio_id": 1,
            "narrative": "texto",
            "source": "llm",
            "model": "qwen3:4b",
            "fallback_reason": None,
        }
        with patch("service.portfolio_narrative", return_value=payload) as m:
            r = c.get("/api/portfolios/1/narrative")
        assert r.status_code == 200
        assert r.json() == payload
        m.assert_called_once_with(1, "us_etf")

    def test_narrative_honors_shelf_query_param(self):
        c = _client()
        payload = {
            "portfolio_id": 1,
            "narrative": "texto",
            "source": "fallback",
            "model": None,
            "fallback_reason": "down",
        }
        with patch("service.portfolio_narrative", return_value=payload) as m:
            r = c.get("/api/portfolios/1/narrative?shelf=br_renda_fixa")
        assert r.status_code == 200
        m.assert_called_once_with(1, "br_renda_fixa")

    def test_narrative_missing_portfolio_returns_404(self):
        c = _client()
        with patch("service.portfolio_narrative", side_effect=ValueError("Portfolio not found: 999")):
            r = c.get("/api/portfolios/999/narrative")
        assert r.status_code == 404

    def test_narrative_unknown_shelf_returns_404(self):
        from runtime.product_mapping import ProductMappingError

        c = _client()
        with patch("service.portfolio_narrative", side_effect=ProductMappingError("Unknown product shelf: 'x'")):
            r = c.get("/api/portfolios/1/narrative?shelf=x")
        assert r.status_code == 404


class TestAssetEndpoints:
    def test_get_asset_success(self):
        c = _client()
        payload = {"symbol": "AAPL", "name": "Apple Inc.", "attributes": {}}
        with patch("service.get_asset", return_value=payload):
            r = c.get("/api/assets/AAPL")
        assert r.status_code == 200
        assert r.json() == payload

    def test_get_asset_missing_returns_404(self):
        c = _client()
        with patch("service.get_asset", side_effect=ValueError("Asset not found: BOGUS")):
            r = c.get("/api/assets/BOGUS")
        assert r.status_code == 404

    def test_tag_asset_success(self):
        c = _client()
        payload = {"symbol": "AAPL", "attributes": {"theme": "AI"}}
        with patch("service.tag_asset", return_value=payload) as m:
            r = c.put("/api/assets/AAPL/attributes", json={"theme": "AI"})
        assert r.status_code == 200
        assert r.json() == payload
        m.assert_called_once()
        assert m.call_args.args[0] == "AAPL"
        assert m.call_args.kwargs["theme"] == "AI"

    def test_tag_asset_request_accepts_every_canonical_field(self):
        """Regression: catches drift between AssetTagRequest and the
        canonical schema at the HTTP layer, not just via introspection."""
        from runtime.portfolio.attributes import ASSET_ATTRIBUTE_FIELDS

        c = _client()
        body = {field: f"v-{field}" for field in ASSET_ATTRIBUTE_FIELDS}
        with patch("service.tag_asset", return_value={"symbol": "AAPL", "attributes": body}) as m:
            r = c.put("/api/assets/AAPL/attributes", json=body)
        assert r.status_code == 200
        assert set(m.call_args.kwargs.keys()) == set(ASSET_ATTRIBUTE_FIELDS)


class TestIntegrationsStatusEndpoint:
    def test_returns_all_integrations(self):
        c = _client()
        fake = [
            {
                "name": "Outlook / Calendar",
                "status": "not_configured",
                "detail": "x",
                "latency_ms": 1.0,
                "checked_at": "t",
            },
            {"name": "WhatsApp", "status": "ok", "detail": "y", "latency_ms": 2.0, "checked_at": "t"},
            {"name": "Ollama", "status": "ok", "detail": "z", "latency_ms": 3.0, "checked_at": "t"},
        ]
        fake_len = len(fake)  # api/router.py copies-then-appends to its own
        # result list rather than mutating service.integrations_status()'s
        # return value, but snapshot the length anyway rather than rely on
        # that — a mock's return_value is a live reference, not a copy.
        with patch("service.integrations_status", return_value=fake):
            r = c.get("/api/integrations/status")
        assert r.status_code == 200
        integrations = r.json()["integrations"]
        assert integrations[:fake_len] == fake
        # api/router.py appends its own "FastAPI" and "CLI" rows — neither is
        # an external reachability probe, so neither is routed through
        # service.py.integrations_status()'s concurrent-check aggregator.
        names_after = [row["name"] for row in integrations[fake_len:]]
        assert names_after == ["FastAPI", "CLI"]
        for row in integrations[fake_len:]:
            assert row["status"] == "ok"
            assert row["error"] is None

    def test_fastapi_row_route_count_matches_app(self):
        from api.router import create_app

        app = create_app(version="test", platform_info={"os_name": "test"})
        c = TestClient(app)
        r = c.get("/api/integrations/status")
        fastapi_row = next(row for row in r.json()["integrations"] if row["name"] == "FastAPI")
        assert str(len(app.routes)) in fastapi_row["detail"]

    def test_cli_row_present(self):
        c = _client()
        r = c.get("/api/integrations/status")
        cli_row = next(row for row in r.json()["integrations"] if row["name"] == "CLI")
        assert cli_row["status"] == "ok"
        assert cli_row["error"] is None


class TestCliStatusEndpoint:
    def test_returns_version_and_commands(self):
        c = _client()
        r = c.get("/api/cli/status")
        assert r.status_code == 200
        data = r.json()
        assert data["version"]
        assert len(data["commands"]) > 0
        for known in ("flow", "outlook", "calendar", "whatsapp", "integrations"):
            assert known in data["commands"]


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
