"""Tests for the human-in-the-loop approval queue HTTP endpoints:
GET /api/agent-approvals, PUT /api/agent-approvals/{id},
POST /api/agent-approvals/{id}/approve, POST /api/agent-approvals/{id}/reject.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests._auth_helper import seed_with_demo_clients, signup_office  # noqa: E402


def _client():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from api.router import create_app

    return TestClient(create_app(version="test"))


def _office_with_pending_approval(contact_info: bool = True):
    """A real office with a real client and a real pending approval,
    exactly the shape agents/orchestrator.py's _handle_client_followup_overdue
    creates -- built directly against the repository (not by running the
    observer loop) so these tests stay focused on the HTTP layer."""
    from storage.agent_approval_repo import AgentApprovalRepository
    from storage.agent_event_repo import AgentEventRepository
    from storage.client_repo import ClientRepository

    client = _client()
    session = signup_office(client)
    seed_with_demo_clients(session["office_id"])
    demo_clients = client.get("/api/clients/demo", headers=session["headers"]).json()["clients"]
    target = next(c for c in demo_clients if c["id"] == "demo-client-27")  # Pimentel Capital, out of band

    async def setup():
        if contact_info:
            await ClientRepository().save_client_contact(session["office_id"], target["id"], "cliente@example.com", None)
        from agents.events import AgentEvent

        event = await AgentEventRepository().publish(
            session["office_id"],
            AgentEvent(type="CLIENT_FOLLOWUP_OVERDUE", source="observer_loop", entity={"kind": "client", "id": target["id"]}),
        )
        return await AgentApprovalRepository().create(
            session["office_id"], event["id"], "followup_agent", "contact_client",
            {"kind": "client", "id": target["id"]},
            {"client_id": target["id"], "client_name": target["name"], "channels": ["email"],
             "draft": {"subject": "Revisão de carteira", "body": "Olá!", "whatsapp_text": "Oi"}},
        )

    approval = asyncio.run(setup())
    return client, session, approval, target


class TestListApprovals:
    def test_requires_auth(self):
        assert _client().get("/api/agent-approvals").status_code == 401

    def test_lists_pending_approval(self):
        client, session, approval, _ = _office_with_pending_approval()
        resp = client.get("/api/agent-approvals", headers=session["headers"])
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["id"] == approval["id"]

    def test_scoped_to_one_office(self):
        client, session_a, _, _ = _office_with_pending_approval()
        session_b = signup_office(client, "Outro Escritório")
        resp = client.get("/api/agent-approvals", headers=session_b["headers"])
        assert resp.json()["total"] == 0

    def test_filters_by_status(self):
        client, session, approval, _ = _office_with_pending_approval()
        client.post(f"/api/agent-approvals/{approval['id']}/reject", headers=session["headers"])
        resp = client.get("/api/agent-approvals?status=pending", headers=session["headers"])
        assert resp.json()["total"] == 0
        resp2 = client.get("/api/agent-approvals?status=rejected", headers=session["headers"])
        assert resp2.json()["total"] == 1


class TestEditApproval:
    def test_requires_auth(self):
        assert _client().put("/api/agent-approvals/x", json={"payload": {}}).status_code == 401

    def test_edit_while_pending(self):
        client, session, approval, _ = _office_with_pending_approval()
        new_payload = {**approval["payload"], "draft": {**approval["payload"]["draft"], "subject": "Editado"}}
        resp = client.put(f"/api/agent-approvals/{approval['id']}", json={"payload": new_payload}, headers=session["headers"])
        assert resp.status_code == 200
        assert resp.json()["approval"]["payload"]["draft"]["subject"] == "Editado"

    def test_unknown_approval_is_404(self):
        client, session, _, _ = _office_with_pending_approval()
        resp = client.put("/api/agent-approvals/nope", json={"payload": {}}, headers=session["headers"])
        assert resp.status_code == 404

    def test_cannot_edit_after_decided(self):
        client, session, approval, _ = _office_with_pending_approval()
        client.post(f"/api/agent-approvals/{approval['id']}/reject", headers=session["headers"])
        resp = client.put(f"/api/agent-approvals/{approval['id']}", json={"payload": approval["payload"]}, headers=session["headers"])
        assert resp.status_code == 409

    def test_cannot_edit_another_offices_approval(self):
        client, session_a, approval, _ = _office_with_pending_approval()
        session_b = signup_office(client, "Outro Escritório")
        resp = client.put(f"/api/agent-approvals/{approval['id']}", json={"payload": approval["payload"]}, headers=session_b["headers"])
        assert resp.status_code == 404


class TestApprove:
    def test_requires_auth(self):
        assert _client().post("/api/agent-approvals/x/approve").status_code == 401

    def test_unknown_approval_is_404(self):
        client, session, _, _ = _office_with_pending_approval()
        resp = client.post("/api/agent-approvals/nope/approve", headers=session["headers"])
        assert resp.status_code == 404

    def test_approve_sends_via_the_real_outreach_pipeline(self):
        client, session, approval, target = _office_with_pending_approval(contact_info=True)
        with patch("runtime.email_sender.is_configured", return_value=True), \
             patch("runtime.email_sender.send_email", return_value={"to": "cliente@example.com"}):
            resp = client.post(f"/api/agent-approvals/{approval['id']}/approve", headers=session["headers"])
        assert resp.status_code == 200
        data = resp.json()["approval"]
        assert data["status"] == "approved"
        assert data["result"]["channels"]["email"]["status"] == "sent"

    def test_approve_with_no_contact_info_reports_honestly(self):
        client, session, approval, target = _office_with_pending_approval(contact_info=False)
        resp = client.post(f"/api/agent-approvals/{approval['id']}/approve", headers=session["headers"])
        assert resp.status_code == 200
        assert resp.json()["approval"]["result"]["channels"]["email"]["status"] == "no_contact_info"

    def test_cannot_approve_twice(self):
        client, session, approval, _ = _office_with_pending_approval()
        with patch("runtime.email_sender.is_configured", return_value=True), \
             patch("runtime.email_sender.send_email", return_value={"to": "x"}):
            client.post(f"/api/agent-approvals/{approval['id']}/approve", headers=session["headers"])
            resp = client.post(f"/api/agent-approvals/{approval['id']}/approve", headers=session["headers"])
        assert resp.status_code == 409

    def test_cannot_approve_another_offices_approval(self):
        client, session_a, approval, _ = _office_with_pending_approval()
        session_b = signup_office(client, "Outro Escritório")
        resp = client.post(f"/api/agent-approvals/{approval['id']}/approve", headers=session_b["headers"])
        assert resp.status_code == 404

    def test_uses_the_clients_current_contact_info_not_a_stale_snapshot(self):
        """Contact info added AFTER the agent proposed the action must
        still be used -- approve() re-fetches the client, it doesn't trust
        whatever the approval payload happened to snapshot."""
        from storage.client_repo import ClientRepository

        client, session, approval, target = _office_with_pending_approval(contact_info=False)
        # Contact info added only now, after the approval was created.
        asyncio.run(ClientRepository().save_client_contact(session["office_id"], target["id"], "novo@example.com", None))

        with patch("runtime.email_sender.is_configured", return_value=True), \
             patch("runtime.email_sender.send_email", return_value={"to": "novo@example.com"}) as mock_send:
            resp = client.post(f"/api/agent-approvals/{approval['id']}/approve", headers=session["headers"])

        assert resp.json()["approval"]["result"]["channels"]["email"]["status"] == "sent"
        mock_send.assert_called_once()
        assert mock_send.call_args[0][0] == "novo@example.com"


class TestReject:
    def test_requires_auth(self):
        assert _client().post("/api/agent-approvals/x/reject").status_code == 401

    def test_reject_never_sends_anything(self):
        client, session, approval, _ = _office_with_pending_approval()
        with patch("runtime.email_sender.send_email") as mock_send:
            resp = client.post(f"/api/agent-approvals/{approval['id']}/reject", headers=session["headers"])
            mock_send.assert_not_called()
        assert resp.status_code == 200
        assert resp.json()["approval"]["status"] == "rejected"
        assert resp.json()["approval"]["result"] is None

    def test_cannot_reject_twice(self):
        client, session, approval, _ = _office_with_pending_approval()
        client.post(f"/api/agent-approvals/{approval['id']}/reject", headers=session["headers"])
        resp = client.post(f"/api/agent-approvals/{approval['id']}/reject", headers=session["headers"])
        assert resp.status_code == 409

    def test_unknown_approval_is_404(self):
        client, session, _, _ = _office_with_pending_approval()
        resp = client.post("/api/agent-approvals/nope/reject", headers=session["headers"])
        assert resp.status_code == 404
