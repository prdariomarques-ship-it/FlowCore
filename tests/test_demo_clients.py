"""Tests for the 27 example client records (Wealth Copilot fase 9,
office-scoped as of fase 0) — explicitly fictitious, explicitly editable
seed data used to populate the multi-client dashboard views. See
runtime/portfolio/demo_clients.py and storage/client_repo.py for why
this is a different category from "never fabricate data": it's
deliberately created, clearly labeled (is_demo=True everywhere), fully
editable/replaceable placeholder data, the same as the reference/model
policy itself.

Low-level repository behavior (seeding, editing, resetting, tenant
isolation) is already covered thoroughly in tests/test_client_repo.py —
this file covers the office-scoped wrapper module
(runtime/portfolio/demo_clients.py), its ComplianceAgent integration,
and the HTTP endpoints.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

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


def _office_with_demo_clients():
    client = _client()
    session = signup_office(client)
    seed_with_demo_clients(session["office_id"])
    return client, session


class TestWrapperModule:
    def test_load_demo_clients_returns_the_seeded_27(self):
        _, session = _office_with_demo_clients()
        from runtime.portfolio.demo_clients import load_demo_clients

        clients = asyncio.run(load_demo_clients(session["office_id"]))
        assert len(clients) == 27
        assert all(c["is_demo"] for c in clients)

    def test_save_and_reset_roundtrip(self):
        _, session = _office_with_demo_clients()
        from runtime.portfolio.demo_clients import load_demo_clients, reset_demo_clients, save_demo_client

        office_id = session["office_id"]
        client_id = asyncio.run(load_demo_clients(office_id))[0]["id"]
        updated = asyncio.run(save_demo_client(office_id, client_id, {"ai_theme": 9.0}))
        assert updated["current_allocation"]["ai_theme"] == 9.0

        asyncio.run(reset_demo_clients(office_id))
        reloaded = next(c for c in asyncio.run(load_demo_clients(office_id)) if c["id"] == client_id)
        assert reloaded["current_allocation"]["ai_theme"] != 9.0

    def test_unknown_client_id_raises(self):
        _, session = _office_with_demo_clients()
        from runtime.portfolio.demo_clients import save_demo_client

        with pytest.raises(KeyError):
            asyncio.run(save_demo_client(session["office_id"], "does-not-exist", {"ai_theme": 1.0}))


class TestComplianceAgentIntegration:
    def test_demo_clients_are_evaluated_and_flagged(self):
        _, session = _office_with_demo_clients()
        from agents.compliance_agent import ComplianceAgent

        result = asyncio.run(ComplianceAgent().run({"office_id": session["office_id"]}))
        portfolios = result["data"]["portfolios"]
        demo_portfolios = [p for p in portfolios if p.get("is_demo")]
        assert len(demo_portfolios) == 27
        # At least one of the deliberately-out-of-band demo clients
        # produces a real violation, and that violation is itself
        # flagged is_demo so the alerts table can label it "exemplo".
        violations = result["data"]["violations"]
        demo_violations = [v for v in violations if v.get("is_demo")]
        assert demo_violations

    def test_reference_portfolio_is_not_flagged_demo(self):
        _, session = _office_with_demo_clients()
        from agents.compliance_agent import ComplianceAgent

        result = asyncio.run(ComplianceAgent().run({"office_id": session["office_id"]}))
        reference = next(p for p in result["data"]["portfolios"] if p["portfolio_id"] == "moderate-ia-1m")
        assert reference.get("is_demo") is False


class TestDemoClientsEndpoints:
    def test_freshly_signed_up_office_has_zero_clients(self):
        """A real signup (not the one-time bootstrap office) must never
        show fabricated clients."""
        client = _client()
        session = signup_office(client)
        resp = client.get("/api/clients/demo", headers=session["headers"])
        assert resp.status_code == 200
        assert resp.json()["clients"] == []

    def test_list_returns_27_for_a_seeded_office(self):
        client, session = _office_with_demo_clients()
        resp = client.get("/api/clients/demo", headers=session["headers"])
        assert resp.status_code == 200
        assert len(resp.json()["clients"]) == 27

    def test_requires_auth(self):
        resp = _client().get("/api/clients/demo")
        assert resp.status_code == 401

    def test_update_unknown_client_is_404(self):
        client, session = _office_with_demo_clients()
        resp = client.put("/api/clients/demo/nope", json={"current_allocation": {"ai_theme": 1.0}}, headers=session["headers"])
        assert resp.status_code == 404

    def test_update_and_reset_roundtrip(self):
        client, session = _office_with_demo_clients()
        client_id = client.get("/api/clients/demo", headers=session["headers"]).json()["clients"][0]["id"]

        put_resp = client.put(
            f"/api/clients/demo/{client_id}", json={"current_allocation": {"ai_theme": 2.0}}, headers=session["headers"]
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["client"]["current_allocation"]["ai_theme"] == 2.0

        reset_resp = client.post("/api/clients/demo/reset", headers=session["headers"])
        assert reset_resp.status_code == 200

    def test_cannot_edit_another_offices_client(self):
        """The API-level version of test_client_repo.py's tenant-isolation
        guarantee: office B's session can never edit office A's client."""
        client, session_a = _office_with_demo_clients()
        session_b = signup_office(client, "Outro Escritório")
        client_id = client.get("/api/clients/demo", headers=session_a["headers"]).json()["clients"][0]["id"]

        resp = client.put(
            f"/api/clients/demo/{client_id}", json={"current_allocation": {"ai_theme": 77.0}}, headers=session_b["headers"]
        )
        assert resp.status_code == 404

    def test_alerts_endpoint_includes_demo_flag(self):
        client, session = _office_with_demo_clients()
        resp = client.get("/api/alerts", headers=session["headers"])
        data = resp.json()
        assert any("is_demo" in item for item in data["items"])

    def test_alerts_endpoint_flags_which_rows_are_real_contactable_clients(self):
        """A violation's client_id can be the office's own reference policy
        (not a real client) — is_client tells the frontend which rows can
        be opened via Client 360 or contacted via outreach without 404ing."""
        client, session = _office_with_demo_clients()
        resp = client.get("/api/alerts", headers=session["headers"])
        data = resp.json()
        assert data["items"], "expected at least one out-of-band demo client"
        assert all(item["is_client"] is True for item in data["items"])


class TestClientCreationEndpoint:
    """POST /api/clients -- previously there was no way to register a
    real client at all (see test_freshly_signed_up_office_has_zero_clients
    above: a fresh office started at zero with no path forward)."""

    def test_requires_auth(self):
        resp = _client().post("/api/clients", json={"name": "Cliente Teste"})
        assert resp.status_code == 401

    def test_creates_a_client_with_just_a_name(self):
        client = _client()
        session = signup_office(client)
        resp = client.post("/api/clients", json={"name": "Família Silva"}, headers=session["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["created"] is True
        assert body["client"]["name"] == "Família Silva"
        assert body["client"]["is_demo"] is False

    def test_empty_name_is_rejected(self):
        client = _client()
        session = signup_office(client)
        resp = client.post("/api/clients", json={"name": "   "}, headers=session["headers"])
        assert resp.status_code == 422

    def test_missing_name_is_rejected(self):
        client = _client()
        session = signup_office(client)
        resp = client.post("/api/clients", json={}, headers=session["headers"])
        assert resp.status_code == 422

    def test_created_client_shows_up_in_the_list(self):
        client = _client()
        session = signup_office(client)
        client.post("/api/clients", json={"name": "Cliente Novo"}, headers=session["headers"])
        resp = client.get("/api/clients/demo", headers=session["headers"])
        names = [c["name"] for c in resp.json()["clients"]]
        assert "Cliente Novo" in names

    def test_created_client_can_then_be_edited_via_the_existing_endpoints(self):
        client = _client()
        session = signup_office(client)
        created = client.post("/api/clients", json={"name": "Editável"}, headers=session["headers"]).json()["client"]

        put_resp = client.put(
            f"/api/clients/demo/{created['id']}",
            json={"current_allocation": {"br_equity_funds": 20.0}}, headers=session["headers"],
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["client"]["current_allocation"]["br_equity_funds"] == 20.0

    def test_full_payload_with_allocation_and_contact(self):
        client = _client()
        session = signup_office(client)
        resp = client.post("/api/clients", json={
            "name": "Cliente Completo", "profile": "arrojado", "reference_value": 750000.0,
            "current_allocation": {"global_equity": 40.0}, "email": "c@example.com", "phone": "+5511988887777",
        }, headers=session["headers"])
        assert resp.status_code == 200
        c = resp.json()["client"]
        assert c["profile"] == "arrojado"
        assert c["reference_value"] == 750000.0
        assert c["current_allocation"] == {"global_equity": 40.0}
        assert c["email"] == "c@example.com"
        assert c["phone"] == "+5511988887777"

    def test_client_created_in_one_office_is_invisible_to_another(self):
        client = _client()
        session_a = signup_office(client)
        session_b = signup_office(client, "Outro Escritório")
        client.post("/api/clients", json={"name": "Só do Escritório A"}, headers=session_a["headers"])

        resp_b = client.get("/api/clients/demo", headers=session_b["headers"])
        assert resp_b.json()["clients"] == []
