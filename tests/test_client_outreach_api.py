"""Tests for the client outreach HTTP endpoints:
PUT /api/clients/demo/{id}/contact, GET /api/clients/review-requests,
POST /api/clients/{id}/request-review.
"""
from __future__ import annotations

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


def _office_with_out_of_band_client():
    """A seeded office with at least one demo client already carrying a
    real violation (Junqueira Capital, +2p.p. over renda_fixa_total per
    config/demo_clients.json), with contact info added so outreach has
    somewhere to send to."""
    client = _client()
    session = signup_office(client)
    seed_with_demo_clients(session["office_id"])
    demo_clients = client.get("/api/clients/demo", headers=session["headers"]).json()["clients"]
    target = next(c for c in demo_clients if c["id"] == "demo-client-21")  # Junqueira Capital, out of band
    client.put(
        f"/api/clients/demo/{target['id']}/contact",
        json={"email": "cliente@example.com", "phone": "5511999999999"},
        headers=session["headers"],
    )
    return client, session, target["id"]


class TestContactUpdate:
    def test_requires_auth(self):
        resp = _client().put("/api/clients/demo/x/contact", json={"email": "a@b.com"})
        assert resp.status_code == 401

    def test_set_and_read_back(self):
        client, session = None, None
        c = _client()
        session = signup_office(c)
        seed_with_demo_clients(session["office_id"])
        client_id = c.get("/api/clients/demo", headers=session["headers"]).json()["clients"][0]["id"]

        resp = c.put(
            f"/api/clients/demo/{client_id}/contact",
            json={"email": "familia@example.com", "phone": "5511988887777"},
            headers=session["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["client"]["email"] == "familia@example.com"

    def test_unknown_client_is_404(self):
        c = _client()
        session = signup_office(c)
        resp = c.put("/api/clients/demo/nope/contact", json={"email": "a@b.com"}, headers=session["headers"])
        assert resp.status_code == 404

    def test_cannot_set_contact_for_another_offices_client(self):
        c = _client()
        session_a = signup_office(c)
        seed_with_demo_clients(session_a["office_id"])
        session_b = signup_office(c, "Outro Escritório")
        client_id = c.get("/api/clients/demo", headers=session_a["headers"]).json()["clients"][0]["id"]

        resp = c.put(
            f"/api/clients/demo/{client_id}/contact", json={"email": "attacker@example.com"},
            headers=session_b["headers"],
        )
        assert resp.status_code == 404


class TestReviewRequestsList:
    def test_requires_auth(self):
        resp = _client().get("/api/clients/review-requests")
        assert resp.status_code == 401

    def test_lists_clients_with_open_violations_and_drafts(self):
        client, session, client_id = _office_with_out_of_band_client()
        resp = client.get("/api/clients/review-requests", headers=session["headers"])
        assert resp.status_code == 200
        data = resp.json()
        item = next(i for i in data["items"] if i["client_id"] == client_id)
        assert item["can_send_email"] is True
        assert item["can_send_whatsapp"] is True
        assert item["draft"]["subject"]
        assert item["is_demo"] is True

    def test_reference_policy_itself_is_never_listed_as_a_contactable_client(self):
        client, session, _ = _office_with_out_of_band_client()
        data = client.get("/api/clients/review-requests", headers=session["headers"]).json()
        assert all(i["client_id"] != "moderate-ia-1m" for i in data["items"])

    def test_clients_without_contact_info_show_false_can_send_flags(self):
        c = _client()
        session = signup_office(c)
        seed_with_demo_clients(session["office_id"])
        data = c.get("/api/clients/review-requests", headers=session["headers"]).json()
        for item in data["items"]:
            assert item["can_send_email"] is False
            assert item["can_send_whatsapp"] is False


class TestRequestReviewSend:
    def test_requires_auth(self):
        resp = _client().post("/api/clients/x/request-review", json={"channels": ["email"]})
        assert resp.status_code == 401

    def test_unknown_client_is_404(self):
        c = _client()
        session = signup_office(c)
        resp = c.post("/api/clients/nope/request-review", json={"channels": ["email"]}, headers=session["headers"])
        assert resp.status_code == 404

    def test_client_without_open_violations_is_400(self):
        c = _client()
        session = signup_office(c)
        seed_with_demo_clients(session["office_id"])
        clients = c.get("/api/clients/demo", headers=session["headers"]).json()["clients"]
        # demo-client-01 ("Família Andrade") sits within every band per config/demo_clients.json
        in_band = next(cl for cl in clients if cl["id"] == "demo-client-01")
        resp = c.post(f"/api/clients/{in_band['id']}/request-review", json={"channels": ["email"]}, headers=session["headers"])
        assert resp.status_code == 400

    def test_no_contact_info_reports_honestly_not_an_error(self):
        c = _client()
        session = signup_office(c)
        seed_with_demo_clients(session["office_id"])
        clients = c.get("/api/clients/demo", headers=session["headers"]).json()["clients"]
        out_of_band = next(cl for cl in clients if cl["id"] == "demo-client-21")["id"]  # Junqueira Capital, no contact set

        resp = c.post(
            f"/api/clients/{out_of_band}/request-review", json={"channels": ["email", "whatsapp"]},
            headers=session["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["channels"]["email"]["status"] == "no_contact_info"
        assert resp.json()["channels"]["whatsapp"]["status"] == "no_contact_info"

    def test_email_sent_end_to_end_with_mocked_transport(self):
        client, session, client_id = _office_with_out_of_band_client()
        with patch("runtime.email_sender.is_configured", return_value=True), \
             patch("runtime.email_sender.send_email", return_value={"to": "cliente@example.com"}):
            resp = client.post(
                f"/api/clients/{client_id}/request-review", json={"channels": ["email"]}, headers=session["headers"],
            )
        assert resp.status_code == 200
        assert resp.json()["channels"]["email"]["status"] == "sent"

    def test_cannot_request_review_for_another_offices_client(self):
        client, session_a, client_id = _office_with_out_of_band_client()
        session_b = signup_office(client, "Outro Escritório")
        resp = client.post(
            f"/api/clients/{client_id}/request-review", json={"channels": ["email"]}, headers=session_b["headers"],
        )
        assert resp.status_code == 404


class TestClient360:
    def test_requires_auth(self):
        resp = _client().get("/api/clients/x/360")
        assert resp.status_code == 401

    def test_unknown_client_is_404(self):
        c = _client()
        session = signup_office(c)
        resp = c.get("/api/clients/nope/360", headers=session["headers"])
        assert resp.status_code == 404

    def test_cannot_view_another_offices_client(self):
        client, session_a, client_id = _office_with_out_of_band_client()
        session_b = signup_office(client, "Outro Escritório")
        resp = client.get(f"/api/clients/{client_id}/360", headers=session_b["headers"])
        assert resp.status_code == 404

    def test_shows_real_client_fields_and_desenquadrado_health(self):
        client, session, client_id = _office_with_out_of_band_client()
        resp = client.get(f"/api/clients/{client_id}/360", headers=session["headers"])
        assert resp.status_code == 200
        data = resp.json()
        assert data["client"]["id"] == client_id
        assert data["client"]["email"] == "cliente@example.com"
        assert data["health"] in ("DESENQUADRADO", "ATENCAO")
        assert len(data["compliance"]["violations"]) > 0

    def test_client_with_no_violations_is_healthy(self):
        c = _client()
        session = signup_office(c)
        seed_with_demo_clients(session["office_id"])
        clients = c.get("/api/clients/demo", headers=session["headers"]).json()["clients"]
        in_band = next(cl for cl in clients if cl["id"] == "demo-client-01")  # Família Andrade
        resp = c.get(f"/api/clients/{in_band['id']}/360", headers=session["headers"])
        assert resp.status_code == 200
        data = resp.json()
        assert data["health"] == "SAUDAVEL"
        assert data["compliance"]["violations"] == []

    def test_includes_outreach_history_after_a_send(self):
        client, session, client_id = _office_with_out_of_band_client()
        with patch("runtime.email_sender.is_configured", return_value=True), \
             patch("runtime.email_sender.send_email", return_value={"to": "cliente@example.com"}):
            client.post(f"/api/clients/{client_id}/request-review", json={"channels": ["email"]}, headers=session["headers"])

        resp = client.get(f"/api/clients/{client_id}/360", headers=session["headers"])
        history = resp.json()["outreach_history"]
        assert len(history) == 1
        assert history[0]["channels"] == ["email"]

    def test_no_outreach_yet_is_an_empty_history_not_an_error(self):
        client, session, client_id = _office_with_out_of_band_client()
        resp = client.get(f"/api/clients/{client_id}/360", headers=session["headers"])
        assert resp.json()["outreach_history"] == []
