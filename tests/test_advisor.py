"""Tests for GET/PUT /api/advisor — the dashboard's Advisor card
(Wealth Copilot fase 10). No photo field on purpose: see the handler's
docstring in api/dashboard_routes.py for why the avatar is initials-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _client():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from api.router import create_app

    return TestClient(create_app(version="test"))


@pytest.fixture(autouse=True)
def _clean_advisor_file():
    path = Path.home() / ".flowcore" / "advisor.json"
    path.unlink(missing_ok=True)
    yield
    path.unlink(missing_ok=True)


class TestAdvisorProfile:
    def test_get_returns_sensible_defaults_with_no_photo_field(self):
        resp = _client().get("/api/advisor")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] and data["title"] and data["quote"]
        assert "photo" not in data and "photo_url" not in data and "image" not in data

    def test_put_partial_update_only_changes_given_fields(self):
        client = _client()
        original = client.get("/api/advisor").json()
        put_resp = client.put("/api/advisor", json={"title": "Head de Investimentos"})
        assert put_resp.status_code == 200
        updated = put_resp.json()
        assert updated["title"] == "Head de Investimentos"
        assert updated["name"] == original["name"]  # untouched field preserved

    def test_put_persists_across_requests(self):
        client = _client()
        client.put("/api/advisor", json={"name": "Teste da Silva"})
        assert client.get("/api/advisor").json()["name"] == "Teste da Silva"
