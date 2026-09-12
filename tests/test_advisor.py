"""Tests for GET/PUT /api/advisor — the dashboard's Advisor card
(Wealth Copilot fase 10, office-scoped as of fase 0; real photo upload
added fase 9-25). No photo means an initials avatar by default — a
photo only ever appears once an advisor uploads a REAL one of
themselves via runtime.advisor_photo.normalize_advisor_photo(); see
that module's docstring for why this is upload-only, never generated.
"""

from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests._auth_helper import signup_office  # noqa: E402


def _fake_photo_data_uri(size=(200, 300), fmt="PNG", color=(120, 40, 200)):
    Image = pytest.importorskip("PIL.Image")
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    mime = "png" if fmt == "PNG" else "jpeg"
    return f"data:image/{mime};base64,{encoded}"


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


class TestAdvisorPhotoUpload:
    def test_uploading_a_real_photo_sets_it_and_persists(self):
        client, session = _session()
        resp = client.put("/api/advisor", json={"photo": _fake_photo_data_uri()}, headers=session["headers"])
        assert resp.status_code == 200
        assert resp.json()["photo"].startswith("data:image/jpeg;base64,")
        assert client.get("/api/advisor", headers=session["headers"]).json()["photo"] == resp.json()["photo"]

    def test_invalid_photo_data_returns_422_and_does_not_persist(self):
        client, session = _session()
        resp = client.put("/api/advisor", json={"photo": "not-a-data-uri"}, headers=session["headers"])
        assert resp.status_code == 422
        assert "photo" not in client.get("/api/advisor", headers=session["headers"]).json()

    def test_empty_string_clears_an_existing_photo(self):
        client, session = _session()
        client.put("/api/advisor", json={"photo": _fake_photo_data_uri()}, headers=session["headers"])
        resp = client.put("/api/advisor", json={"photo": ""}, headers=session["headers"])
        assert resp.status_code == 200
        assert "photo" not in resp.json()
        assert "photo" not in client.get("/api/advisor", headers=session["headers"]).json()

    def test_omitting_photo_leaves_an_existing_one_untouched(self):
        client, session = _session()
        photo = client.put("/api/advisor", json={"photo": _fake_photo_data_uri()}, headers=session["headers"]).json()[
            "photo"
        ]
        client.put("/api/advisor", json={"title": "Novo Cargo"}, headers=session["headers"])
        assert client.get("/api/advisor", headers=session["headers"]).json()["photo"] == photo

    def test_two_offices_have_independent_photos(self):
        client, session_a = _session()
        session_b = signup_office(client, "Outro Escritório com Foto")
        client.put("/api/advisor", json={"photo": _fake_photo_data_uri()}, headers=session_a["headers"])
        assert "photo" not in client.get("/api/advisor", headers=session_b["headers"]).json()
