"""Tests for the autonomous Agent Runtime's observability + notification
config endpoints: GET /api/agent-events, GET/PUT /api/office/notifications.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests._auth_helper import signup_office  # noqa: E402


def _client():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from api.router import create_app

    return TestClient(create_app(version="test"))


class TestAgentEventsList:
    def test_requires_auth(self):
        resp = _client().get("/api/agent-events")
        assert resp.status_code == 401

    def test_empty_when_nothing_published_yet(self):
        c = _client()
        session = signup_office(c)
        resp = c.get("/api/agent-events", headers=session["headers"])
        assert resp.status_code == 200
        assert resp.json() == {"total": 0, "items": []}

    def test_lists_published_events_for_this_office_only(self):
        import asyncio

        from agents.events import AgentEvent
        from storage.agent_event_repo import AgentEventRepository

        c = _client()
        session_a = signup_office(c)
        session_b = signup_office(c, "Outro Escritório")

        event = AgentEvent(
            type="PORTFOLIO_OUT_OF_PROFILE", source="compliance_agent", entity={"kind": "client", "id": "c1"}
        )
        asyncio.run(AgentEventRepository().publish(session_a["office_id"], event))

        resp_a = c.get("/api/agent-events", headers=session_a["headers"])
        resp_b = c.get("/api/agent-events", headers=session_b["headers"])
        assert resp_a.json()["total"] == 1
        assert resp_b.json()["total"] == 0

    def test_filters_by_status(self):
        import asyncio

        from agents.events import AgentEvent
        from storage.agent_event_repo import AgentEventRepository

        c = _client()
        session = signup_office(c)
        repo = AgentEventRepository()

        async def seed():
            pending = await repo.publish(
                session["office_id"], AgentEvent(type="X", source="s", entity={"kind": "client", "id": "c1"})
            )
            processed = await repo.publish(
                session["office_id"], AgentEvent(type="X", source="s", entity={"kind": "client", "id": "c2"})
            )
            await repo.record_decision(session["office_id"], processed["id"], "processed", {"action": "notify_advisor"})
            return pending

        pending = asyncio.run(seed())
        resp = c.get("/api/agent-events?status=pending", headers=session["headers"])
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == pending["id"]


class TestOfficeNotifications:
    def test_requires_auth_get(self):
        assert _client().get("/api/office/notifications").status_code == 401

    def test_requires_auth_put(self):
        assert _client().put("/api/office/notifications", json={"telegram_chat_id": "-100"}).status_code == 401

    def test_defaults_to_none(self):
        c = _client()
        session = signup_office(c)
        resp = c.get("/api/office/notifications", headers=session["headers"])
        assert resp.json() == {"telegram_chat_id": None}

    def test_set_and_read_back(self):
        c = _client()
        session = signup_office(c)
        put_resp = c.put(
            "/api/office/notifications", json={"telegram_chat_id": "-100123456"}, headers=session["headers"]
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["telegram_chat_id"] == "-100123456"

        get_resp = c.get("/api/office/notifications", headers=session["headers"])
        assert get_resp.json()["telegram_chat_id"] == "-100123456"

    def test_clear_by_sending_null(self):
        c = _client()
        session = signup_office(c)
        c.put("/api/office/notifications", json={"telegram_chat_id": "-100123456"}, headers=session["headers"])
        cleared = c.put("/api/office/notifications", json={"telegram_chat_id": None}, headers=session["headers"])
        assert cleared.json()["telegram_chat_id"] is None

    def test_scoped_to_one_office(self):
        c = _client()
        session_a = signup_office(c)
        session_b = signup_office(c, "Outro Escritório")
        c.put("/api/office/notifications", json={"telegram_chat_id": "-100AAA"}, headers=session_a["headers"])

        resp_b = c.get("/api/office/notifications", headers=session_b["headers"])
        assert resp_b.json()["telegram_chat_id"] is None


class TestDiscoverChatId:
    def test_requires_auth(self):
        assert _client().get("/api/office/notifications/discover-chat-id").status_code == 401

    def test_not_configured_when_no_bot_token(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        c = _client()
        session = signup_office(c)
        resp = c.get("/api/office/notifications/discover-chat-id", headers=session["headers"])
        assert resp.status_code == 200
        assert resp.json() == {"available": False, "reason": "not_configured", "chats": []}

    def test_returns_chats_from_telegram(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        c = _client()
        session = signup_office(c)
        found = [{"chat_id": "883232211", "name": "Dário marques", "type": "private"}]
        with patch("runtime.telegram.get_recent_chats", return_value=found):
            resp = c.get("/api/office/notifications/discover-chat-id", headers=session["headers"])
        assert resp.json() == {"available": True, "chats": found}

    def test_telegram_error_reported_honestly(self, monkeypatch):
        from runtime.telegram import TelegramError

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        c = _client()
        session = signup_office(c)
        with patch("runtime.telegram.get_recent_chats", side_effect=TelegramError("Telegram unreachable")):
            resp = c.get("/api/office/notifications/discover-chat-id", headers=session["headers"])
        body = resp.json()
        assert body["available"] is False
        assert body["chats"] == []
        assert "unreachable" in body["reason"]


class TestNotificationTestSend:
    """POST /api/office/notifications/test -- an on-demand real send so a
    silent Telegram pipeline (CoreOrchestrator's _send_telegram swallows
    failures into an "ignored" agent event) can be diagnosed immediately
    instead of waiting for a real portfolio violation to trigger it."""

    def test_requires_auth(self):
        assert _client().post("/api/office/notifications/test").status_code == 401

    def test_no_chat_id_configured(self):
        c = _client()
        session = signup_office(c)
        resp = c.post("/api/office/notifications/test", headers=session["headers"])
        assert resp.status_code == 200
        assert resp.json() == {
            "sent": False,
            "reason": "no_chat_id",
            "detail": "Nenhum chat_id configurado para este escritório. Configure em Ajustes.",
        }

    def test_bot_token_missing_on_server(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        c = _client()
        session = signup_office(c)
        c.put("/api/office/notifications", json={"telegram_chat_id": "883232211"}, headers=session["headers"])

        resp = c.post("/api/office/notifications/test", headers=session["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["sent"] is False
        assert body["reason"] == "bot_not_configured"

    def test_real_telegram_error_surfaced_honestly(self, monkeypatch):
        from runtime.telegram import TelegramError

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        c = _client()
        session = signup_office(c)
        c.put("/api/office/notifications", json={"telegram_chat_id": "883232211"}, headers=session["headers"])

        with patch(
            "runtime.telegram.send_message",
            side_effect=TelegramError("Telegram API error 403: bot was blocked by the user"),
        ):
            resp = c.post("/api/office/notifications/test", headers=session["headers"])
        body = resp.json()
        assert body["sent"] is False
        assert body["reason"] == "telegram_error"
        assert "blocked" in body["detail"]

    def test_success_sends_to_the_configured_chat_id(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        c = _client()
        session = signup_office(c)
        c.put("/api/office/notifications", json={"telegram_chat_id": "883232211"}, headers=session["headers"])

        with patch("runtime.telegram.send_message", return_value={"message_id": 1}) as mocked_send:
            resp = c.post("/api/office/notifications/test", headers=session["headers"])
        assert resp.json() == {"sent": True, "chat_id": "883232211"}
        mocked_send.assert_called_once()
        args = mocked_send.call_args[0]
        assert args[1] == "883232211"
