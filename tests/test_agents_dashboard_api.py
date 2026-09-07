"""Tests for GET /api/agents/dashboard -- the Agent Runtime observability
panel's single aggregating endpoint (§18/§25): scheduler status, event
and approval counts, LLM cost summary, and a recent-activity feed.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

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


class TestAgentsDashboard:
    def test_requires_auth(self):
        resp = _client().get("/api/agents/dashboard")
        assert resp.status_code == 401

    def test_shape_with_nothing_recorded_yet(self):
        c = _client()
        session = signup_office(c)
        resp = c.get("/api/agents/dashboard", headers=session["headers"])
        assert resp.status_code == 200
        body = resp.json()

        # version="test" never wires app.state.agent_scheduler at all (see
        # api/router.py's version-gated block) -- the endpoint must treat
        # that as "disabled", not crash on a missing attribute.
        assert body["scheduler"] == {
            "enabled": False, "running": False,
            "interval_seconds": body["scheduler"]["interval_seconds"], "tasks": [],
        }
        assert body["events"] == {"by_status": {}, "by_type": {}, "total": 0}
        assert body["approvals"] == {"by_status": {}, "pending": 0}
        assert body["recent_activity"] == []
        for window in ("today", "last_7d", "last_30d"):
            assert body["llm_usage"][window]["total_calls"] >= 0

    def test_reflects_published_events_and_approvals(self):
        from agents.events import AgentEvent
        from storage.agent_approval_repo import AgentApprovalRepository
        from storage.agent_event_repo import AgentEventRepository

        c = _client()
        session = signup_office(c)
        office_id = session["office_id"]

        async def seed():
            event_repo = AgentEventRepository()
            published = await event_repo.publish(
                office_id, AgentEvent(type="PORTFOLIO_OUT_OF_PROFILE", source="compliance_agent", entity={"kind": "client", "id": "c1"}),
            )
            await event_repo.record_decision(office_id, published["id"], "processed", {"action": "notify_advisor"})
            await AgentApprovalRepository().create(
                office_id, published["id"], "followup_agent", "contact_client",
                {"kind": "client", "id": "c1"}, {"client_id": "c1", "client_name": "Teste", "draft": {}, "channels": ["email"]},
            )

        asyncio.run(seed())
        resp = c.get("/api/agents/dashboard", headers=session["headers"])
        body = resp.json()
        assert body["events"] == {"by_status": {"processed": 1}, "by_type": {"PORTFOLIO_OUT_OF_PROFILE": 1}, "total": 1}
        assert body["approvals"] == {"by_status": {"pending": 1}, "pending": 1}
        assert len(body["recent_activity"]) == 1

    def test_scoped_to_the_authenticated_office(self):
        import asyncio as _asyncio

        from agents.events import AgentEvent
        from storage.agent_event_repo import AgentEventRepository

        c = _client()
        session_a = signup_office(c)
        session_b = signup_office(c, "Outro Escritório")

        _asyncio.run(AgentEventRepository().publish(
            session_a["office_id"], AgentEvent(type="X", source="s", entity={"kind": "client", "id": "c1"}),
        ))

        resp_b = c.get("/api/agents/dashboard", headers=session_b["headers"])
        assert resp_b.json()["events"]["total"] == 0

    def test_llm_usage_scoped_to_the_authenticated_office(self):
        from storage.llm_call_repo import LLMCallRepository

        c = _client()
        session_a = signup_office(c)
        session_b = signup_office(c, "Outro Escritório")

        repo = LLMCallRepository()
        repo.record_call("deepseek", "deepseek-chat", 100.0, True, None, tokens=250, office_id=session_a["office_id"])
        repo.record_call("deepseek", "deepseek-chat", 100.0, True, None, tokens=999, office_id=session_b["office_id"])

        body_a = c.get("/api/agents/dashboard", headers=session_a["headers"]).json()
        assert body_a["llm_usage"]["today"]["total_calls"] == 1
        assert body_a["llm_usage"]["today"]["total_tokens"] == 250
