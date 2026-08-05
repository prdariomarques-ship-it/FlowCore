"""Tests for service.py's Integration Dashboard aggregator (Sprint 17,
Milestone 6). Live-probe only, no history — these test that each
per-service check classifies status correctly and that the aggregator
adds latency_ms/checked_at without losing per-check detail.

Each runtime module's own real behavior is covered in its own test file
(tests/test_microsoft_graph.py, tests/test_whatsapp.py, and Ollama's
existing coverage) — this file mocks at the service.py boundary.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# _check_outlook/_check_whatsapp import runtime.microsoft_graph/runtime.whatsapp
# locally, which need msal/requests (requirements-api.txt, optional) — skip
# gracefully on a core-only install instead of failing (same pattern as
# tests/test_outlook.py and tests/test_whatsapp.py).
msal = pytest.importorskip("msal")
requests = pytest.importorskip("requests")


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for var in ("OUTLOOK_CLIENT_ID", "OUTLOOK_TENANT_ID", "EVOLUTION_API_KEY", "EVOLUTION_INSTANCE_NAME"):
        monkeypatch.delenv(var, raising=False)


class TestCheckOutlook:
    def test_not_configured(self):
        import asyncio

        import service

        result = asyncio.run(service._check_outlook())
        assert result["status"] == "not_configured"
        assert result["error"] is None

    def test_configured_and_authenticated(self, monkeypatch):
        import asyncio

        import service

        monkeypatch.setenv("OUTLOOK_CLIENT_ID", "abc")
        with patch("runtime.microsoft_graph.is_authenticated", return_value=True):
            result = asyncio.run(service._check_outlook())
        assert result["status"] == "ok"
        assert result["error"] is None

    def test_configured_but_not_authenticated(self, monkeypatch):
        import asyncio

        import service

        monkeypatch.setenv("OUTLOOK_CLIENT_ID", "abc")
        with patch("runtime.microsoft_graph.is_authenticated", return_value=False):
            result = asyncio.run(service._check_outlook())
        assert result["status"] == "not_authenticated"
        assert result["error"] is None


class TestCheckOutlookMailbox:
    def test_not_configured(self):
        import asyncio

        import service

        result = asyncio.run(service._check_outlook_mailbox())
        assert result["status"] == "not_configured"

    def test_ok(self, monkeypatch):
        import asyncio

        import service

        monkeypatch.setenv("OUTLOOK_CLIENT_ID", "abc")
        with (
            patch("runtime.microsoft_graph.is_authenticated", return_value=True),
            patch("runtime.outlook.get_unread_count", return_value=7),
        ):
            result = asyncio.run(service._check_outlook_mailbox())
        assert result["status"] == "ok"
        assert "7 unread" in result["detail"]
        assert result["error"] is None

    def test_error(self, monkeypatch):
        import asyncio

        import service
        from runtime.outlook import OutlookError

        monkeypatch.setenv("OUTLOOK_CLIENT_ID", "abc")
        with (
            patch("runtime.microsoft_graph.is_authenticated", return_value=True),
            patch("runtime.outlook.get_unread_count", side_effect=OutlookError("graph down")),
        ):
            result = asyncio.run(service._check_outlook_mailbox())
        assert result["status"] == "error"
        assert result["error"] == "graph down"


class TestCheckOutlookCalendar:
    def test_not_configured(self):
        import asyncio

        import service

        result = asyncio.run(service._check_outlook_calendar())
        assert result["status"] == "not_configured"

    def test_ok(self, monkeypatch):
        import asyncio

        import service

        monkeypatch.setenv("OUTLOOK_CLIENT_ID", "abc")
        with (
            patch("runtime.microsoft_graph.is_authenticated", return_value=True),
            patch("runtime.calendar.list_today", return_value=[{"subject": "Standup"}]),
        ):
            result = asyncio.run(service._check_outlook_calendar())
        assert result["status"] == "ok"
        assert "1 events today" in result["detail"]
        assert result["error"] is None

    def test_error(self, monkeypatch):
        import asyncio

        import service
        from runtime.calendar import CalendarError

        monkeypatch.setenv("OUTLOOK_CLIENT_ID", "abc")
        with (
            patch("runtime.microsoft_graph.is_authenticated", return_value=True),
            patch("runtime.calendar.list_today", side_effect=CalendarError("graph down")),
        ):
            result = asyncio.run(service._check_outlook_calendar())
        assert result["status"] == "error"
        assert result["error"] == "graph down"


class TestCheckWhatsApp:
    def test_unreachable(self):
        import asyncio

        import service
        from runtime.whatsapp import WhatsAppError

        with patch("runtime.whatsapp.check_health", side_effect=WhatsAppError("refused")):
            result = asyncio.run(service._check_whatsapp())
        assert result["status"] == "unreachable"
        assert result["error"] == "refused"

    def test_reachable_not_configured(self):
        import asyncio

        import service

        with patch("runtime.whatsapp.check_health", return_value={"version": "2.2.3"}):
            result = asyncio.run(service._check_whatsapp())
        assert result["status"] == "not_configured"
        assert "2.2.3" in result["detail"]
        assert result["error"] is None

    def test_reachable_configured_open(self, monkeypatch):
        import asyncio

        import service

        monkeypatch.setenv("EVOLUTION_API_KEY", "key")
        monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "inst")
        with (
            patch("runtime.whatsapp.check_health", return_value={"version": "2.2.3"}),
            patch("runtime.whatsapp.get_status", return_value={"instance": {"state": "open"}}),
        ):
            result = asyncio.run(service._check_whatsapp())
        assert result["status"] == "ok"
        assert result["error"] is None

    def test_reachable_configured_closed(self, monkeypatch):
        import asyncio

        import service

        monkeypatch.setenv("EVOLUTION_API_KEY", "key")
        monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "inst")
        with (
            patch("runtime.whatsapp.check_health", return_value={"version": "2.2.3"}),
            patch("runtime.whatsapp.get_status", return_value={"instance": {"state": "close"}}),
        ):
            result = asyncio.run(service._check_whatsapp())
        assert result["status"] == "error"
        assert result["error"] is not None


class TestCheckOllama:
    def test_unreachable(self):
        import asyncio

        import service
        from runtime.ollama import OllamaDiscoveryError

        with patch("runtime.ollama.discover_ollama_endpoint", side_effect=OllamaDiscoveryError("no host")):
            result = asyncio.run(service._check_ollama())
        assert result["status"] == "unreachable"
        assert result["error"] == "no host"

    def test_ok(self):
        import asyncio

        import service

        with (
            patch("runtime.ollama.discover_ollama_endpoint", return_value="http://127.0.0.1:11434"),
            patch("runtime.ollama.discover_default_model", return_value="qwen3:4b"),
        ):
            result = asyncio.run(service._check_ollama())
        assert result["status"] == "ok"
        assert "qwen3:4b" in result["detail"]
        assert result["error"] is None


class TestCheckAndroid:
    def test_none_available(self):
        import asyncio

        import service

        with patch.object(service._registry, "get", return_value=None):
            result = asyncio.run(service._check_android())
        assert result["status"] == "unreachable"
        assert result["capabilities"] == []

    def test_all_available(self):
        import asyncio

        import service

        with patch.object(service._registry, "get", return_value=object()):
            result = asyncio.run(service._check_android())
        assert result["status"] == "ok"
        assert len(result["capabilities"]) == 5
        assert "All 5 capabilities available" in result["detail"]

    def test_partial_availability(self):
        import asyncio

        import service

        def fake_get(capability):
            return object() if capability in ("getBattery", "getNetworkInfo") else None

        with patch.object(service._registry, "get", side_effect=fake_get):
            result = asyncio.run(service._check_android())
        assert result["status"] == "ok"
        assert set(result["capabilities"]) == {"getBattery", "getNetworkInfo"}
        assert "2/5 available" in result["detail"]

    def test_does_not_call_capabilities_with_side_effects(self):
        import asyncio

        import service

        with (
            patch.object(service._registry, "get", return_value=object()) as mock_get,
            patch.object(service._registry, "call") as mock_call,
        ):
            asyncio.run(service._check_android())
        mock_get.assert_called()
        mock_call.assert_not_called()


class TestIntegrationsStatus:
    @staticmethod
    def _ok(detail: str) -> AsyncMock:
        return AsyncMock(return_value={"status": "ok", "detail": detail, "error": None})

    def test_aggregates_all_five_with_latency_and_timestamp(self):
        import asyncio

        import service

        with (
            patch.object(service, "_check_outlook", new=self._ok("a")),
            patch.object(service, "_check_outlook_mailbox", new=self._ok("b")),
            patch.object(service, "_check_outlook_calendar", new=self._ok("c")),
            patch.object(service, "_check_whatsapp", new=self._ok("y")),
            patch.object(service, "_check_ollama", new=self._ok("z")),
            patch.object(service, "_check_android", new=self._ok("w")),
        ):
            results = asyncio.run(service.integrations_status())
        assert len(results) == 6
        names = {r["name"] for r in results}
        assert names == {"Outlook Auth", "Outlook Mailbox", "Outlook Calendar", "WhatsApp", "Ollama", "Android"}
        for r in results:
            assert "latency_ms" in r
            assert "checked_at" in r
            assert r["status"] == "ok"
            assert r["error"] is None

    def test_one_check_raising_does_not_break_the_others(self):
        import asyncio

        import service

        with (
            patch.object(service, "_check_outlook", new=AsyncMock(side_effect=RuntimeError("boom"))),
            patch.object(service, "_check_outlook_mailbox", new=self._ok("b")),
            patch.object(service, "_check_outlook_calendar", new=self._ok("c")),
            patch.object(service, "_check_whatsapp", new=self._ok("y")),
            patch.object(service, "_check_ollama", new=self._ok("z")),
            patch.object(service, "_check_android", new=self._ok("w")),
        ):
            results = asyncio.run(service.integrations_status())
        assert len(results) == 6
        outlook_result = next(r for r in results if r["name"] == "Outlook Auth")
        assert outlook_result["status"] == "error"
        assert "boom" in outlook_result["detail"]
        assert outlook_result["error"] == "boom"
