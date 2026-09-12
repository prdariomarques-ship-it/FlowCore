"""Tests for the investor classification HTTP endpoints:
GET /api/investor-classification/rules, PUT /api/clients/{id}/investor-classification.
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


class TestInvestorClassificationRules:
    def test_requires_auth(self):
        resp = _client().get("/api/investor-classification/rules")
        assert resp.status_code == 401

    def test_returns_thresholds_and_certifications(self):
        c = _client()
        session = signup_office(c)
        resp = c.get("/api/investor-classification/rules", headers=session["headers"])
        assert resp.status_code == 200
        data = resp.json()
        assert data["qualified_threshold"] == 1_000_000.0
        assert data["professional_threshold"] == 10_000_000.0
        assert "CEA" in data["accepted_certifications"]
        assert "profissional" in data["category_labels"]


class TestInvestorClassificationUpdate:
    def test_requires_auth(self):
        resp = _client().put("/api/clients/x/investor-classification", json={"declared_investments": 5_000_000})
        assert resp.status_code == 401

    def test_unknown_client_is_404(self):
        c = _client()
        session = signup_office(c)
        resp = c.put(
            "/api/clients/nope/investor-classification",
            json={"declared_investments": 5_000_000},
            headers=session["headers"],
        )
        assert resp.status_code == 404

    def test_sets_category_from_declared_investments(self):
        c = _client()
        session = signup_office(c)
        created = c.post(
            "/api/clients", json={"name": "Cliente Rico"}, headers=session["headers"],
        ).json()["client"]

        resp = c.put(
            f"/api/clients/{created['id']}/investor-classification",
            json={"declared_investments": 15_000_000.0},
            headers=session["headers"],
        )
        assert resp.status_code == 200
        data = resp.json()["client"]
        assert data["investor_category"] == "profissional"
        assert data["investor_attestation_at"] is not None

    def test_sets_category_from_certification_alone(self):
        c = _client()
        session = signup_office(c)
        created = c.post(
            "/api/clients", json={"name": "Cliente Certificado"}, headers=session["headers"],
        ).json()["client"]

        resp = c.put(
            f"/api/clients/{created['id']}/investor-classification",
            json={"certification": "cea"},
            headers=session["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["client"]["investor_category"] == "qualificado"

    def test_a_new_client_starts_as_geral(self):
        c = _client()
        session = signup_office(c)
        created = c.post(
            "/api/clients", json={"name": "Cliente Padrão"}, headers=session["headers"],
        ).json()["client"]
        assert created["investor_category"] == "geral"

    def test_cannot_classify_a_client_from_another_office(self):
        c = _client()
        session_a = signup_office(c)
        session_b = signup_office(c)
        created = c.post(
            "/api/clients", json={"name": "Cliente A"}, headers=session_a["headers"],
        ).json()["client"]

        resp = c.put(
            f"/api/clients/{created['id']}/investor-classification",
            json={"declared_investments": 20_000_000.0},
            headers=session_b["headers"],
        )
        assert resp.status_code == 404
