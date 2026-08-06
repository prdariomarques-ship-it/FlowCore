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

    def test_configured_and_authenticated(self, monkeypatch):
        import asyncio

        import service

        monkeypatch.setenv("OUTLOOK_CLIENT_ID", "abc")
        with patch("runtime.microsoft_graph.is_authenticated", return_value=True):
            result = asyncio.run(service._check_outlook())
        assert result["status"] == "ok"

    def test_configured_but_not_authenticated(self, monkeypatch):
        import asyncio

        import service

        monkeypatch.setenv("OUTLOOK_CLIENT_ID", "abc")
        with patch("runtime.microsoft_graph.is_authenticated", return_value=False):
            result = asyncio.run(service._check_outlook())
        assert result["status"] == "not_authenticated"


class TestCheckWhatsApp:
    def test_unreachable(self):
        import asyncio

        import service
        from runtime.whatsapp import WhatsAppError

        with patch("runtime.whatsapp.check_health", side_effect=WhatsAppError("refused")):
            result = asyncio.run(service._check_whatsapp())
        assert result["status"] == "unreachable"

    def test_reachable_not_configured(self):
        import asyncio

        import service

        with patch("runtime.whatsapp.check_health", return_value={"version": "2.2.3"}):
            result = asyncio.run(service._check_whatsapp())
        assert result["status"] == "not_configured"
        assert "2.2.3" in result["detail"]

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


class TestCheckOllama:
    def test_unreachable(self):
        import asyncio

        import service
        from runtime.ollama import OllamaDiscoveryError

        with patch("runtime.ollama.discover_ollama_endpoint", side_effect=OllamaDiscoveryError("no host")):
            result = asyncio.run(service._check_ollama())
        assert result["status"] == "unreachable"

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


class TestIntegrationsStatus:
    def test_aggregates_all_three_with_latency_and_timestamp(self):
        import asyncio

        import service

        with (
            patch.object(service, "_check_outlook", new=AsyncMock(return_value={"status": "ok", "detail": "x"})),
            patch.object(service, "_check_whatsapp", new=AsyncMock(return_value={"status": "ok", "detail": "y"})),
            patch.object(service, "_check_ollama", new=AsyncMock(return_value={"status": "ok", "detail": "z"})),
        ):
            results = asyncio.run(service.integrations_status())
        assert len(results) == 3
        names = {r["name"] for r in results}
        assert names == {"Outlook / Calendar", "WhatsApp", "Ollama"}
        for r in results:
            assert "latency_ms" in r
            assert "checked_at" in r
            assert r["status"] == "ok"

    def test_one_check_raising_does_not_break_the_others(self):
        import asyncio

        import service

        with (
            patch.object(service, "_check_outlook", new=AsyncMock(side_effect=RuntimeError("boom"))),
            patch.object(service, "_check_whatsapp", new=AsyncMock(return_value={"status": "ok", "detail": "y"})),
            patch.object(service, "_check_ollama", new=AsyncMock(return_value={"status": "ok", "detail": "z"})),
        ):
            results = asyncio.run(service.integrations_status())
        assert len(results) == 3
        outlook_result = next(r for r in results if r["name"] == "Outlook / Calendar")
        assert outlook_result["status"] == "error"
        assert "boom" in outlook_result["detail"]
