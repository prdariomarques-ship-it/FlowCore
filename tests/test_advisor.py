"""Tests for GET/PUT /api/advisor — the dashboard's Advisor card
(Wealth Copilot fase 10, office-scoped as of fase 0). No photo field on
purpose: see the handler's docstring in api/dashboard_routes.py for why
the avatar is initials-only.
"""
from __future__ import annotations

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


def _session():
    client = _client()
    return client, signup_office(client)


class TestAdvisorProfile:
    def test_requires_auth(self):
        resp = _client().get("/api/advisor")
        assert resp.status_code == 401

    def test_get_defaults_to_the_signed_up_users_own_name_no_photo_field(self):
        client, session = _session()
        resp = client.get("/api/advisor", headers=session["headers"])
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == session["user"]["name"]
        assert data["title"] and data["quote"]
        assert "photo" not in data and "photo_url" not in data and "image" not in data

    def test_put_partial_update_only_changes_given_fields(self):
        client, session = _session()
        original = client.get("/api/advisor", headers=session["headers"]).json()
        put_resp = client.put("/api/advisor", json={"title": "Head de Investimentos"}, headers=session["headers"])
        assert put_resp.status_code == 200
        updated = put_resp.json()
        assert updated["title"] == "Head de Investimentos"
        assert updated["name"] == original["name"]  # untouched field preserved

    def test_put_persists_across_requests(self):
        client, session = _session()
        client.put("/api/advisor", json={"name": "Teste da Silva"}, headers=session["headers"])
        assert client.get("/api/advisor", headers=session["headers"]).json()["name"] == "Teste da Silva"

    def test_two_offices_have_independent_advisor_profiles(self):
        client, session_a = _session()
        session_b = signup_office(client, "Outro Escritório")
        client.put("/api/advisor", json={"name": "Nome do Escritório A"}, headers=session_a["headers"])
        name_b = client.get("/api/advisor", headers=session_b["headers"]).json()["name"]
        assert name_b != "Nome do Escritório A"
