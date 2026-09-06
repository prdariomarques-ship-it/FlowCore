"""Tests for POST /api/auth/signup, /login, /logout and GET /api/auth/me
(fase 0 multi-office auth) — the HTTP-level counterpart to
tests/test_tenant_repo.py's repository tests, including the OWASP-
aligned password policy and login throttling added after reviewing
OWASP's Password Storage and Authentication Cheat Sheets.
"""
from __future__ import annotations

import sys
import uuid
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


def _unique_email() -> str:
    return f"test-{uuid.uuid4().hex}@example.com"


class TestSignupValidation:
    def test_password_shorter_than_8_is_rejected(self):
        resp = _client().post("/api/auth/signup", json={
            "office_name": "Escritório", "name": "Teste", "email": _unique_email(), "password": "curta",
        })
        assert resp.status_code == 422

    def test_password_longer_than_128_is_rejected(self):
        resp = _client().post("/api/auth/signup", json={
            "office_name": "Escritório", "name": "Teste", "email": _unique_email(), "password": "a" * 129,
        })
        assert resp.status_code == 422

    def test_password_at_minimum_length_is_accepted(self):
        resp = _client().post("/api/auth/signup", json={
            "office_name": "Escritório", "name": "Teste", "email": _unique_email(), "password": "12345678",
        })
        assert resp.status_code == 200

    def test_malformed_email_is_rejected(self):
        resp = _client().post("/api/auth/signup", json={
            "office_name": "Escritório", "name": "Teste", "email": "not-an-email", "password": "senha-valida-123",
        })
        assert resp.status_code == 422

    def test_duplicate_email_is_409(self):
        client = _client()
        email = _unique_email()
        first = client.post("/api/auth/signup", json={
            "office_name": "A", "name": "A", "email": email, "password": "senha-valida-123",
        })
        assert first.status_code == 200
        second = client.post("/api/auth/signup", json={
            "office_name": "B", "name": "B", "email": email, "password": "outra-senha-456",
        })
        assert second.status_code == 409

    def test_response_never_includes_password_fields(self):
        resp = _client().post("/api/auth/signup", json={
            "office_name": "Escritório", "name": "Teste", "email": _unique_email(), "password": "senha-valida-123",
        })
        body = resp.text.lower()
        assert "password_hash" not in body and "password_salt" not in body


class TestLoginAndLogout:
    def test_login_with_correct_password_succeeds(self):
        client = _client()
        email = _unique_email()
        client.post("/api/auth/signup", json={
            "office_name": "Escritório", "name": "Teste", "email": email, "password": "senha-correta-123",
        })
        resp = client.post("/api/auth/login", json={"email": email, "password": "senha-correta-123"})
        assert resp.status_code == 200
        assert resp.json()["token"]

    def test_login_with_wrong_password_is_401(self):
        client = _client()
        email = _unique_email()
        client.post("/api/auth/signup", json={
            "office_name": "Escritório", "name": "Teste", "email": email, "password": "senha-correta-123",
        })
        resp = client.post("/api/auth/login", json={"email": email, "password": "senha-errada"})
        assert resp.status_code == 401

    def test_login_with_unknown_email_is_401_not_404(self):
        # Never reveal via status code whether an email is registered.
        resp = _client().post("/api/auth/login", json={"email": _unique_email(), "password": "qualquer-coisa"})
        assert resp.status_code == 401

    def test_me_requires_a_valid_token(self):
        resp = _client().get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_returns_the_logged_in_user(self):
        client = _client()
        session = signup_office(client)
        resp = client.get("/api/auth/me", headers=session["headers"])
        assert resp.status_code == 200
        assert resp.json()["id"] == session["user"]["id"]

    def test_logout_invalidates_the_token(self):
        client = _client()
        session = signup_office(client)
        assert client.get("/api/auth/me", headers=session["headers"]).status_code == 200
        client.post("/api/auth/logout", headers=session["headers"])
        assert client.get("/api/auth/me", headers=session["headers"]).status_code == 401


class TestLoginRateLimiting:
    def test_sixth_consecutive_failed_attempt_is_429(self):
        client = _client()
        email = _unique_email()
        client.post("/api/auth/signup", json={
            "office_name": "Escritório", "name": "Teste", "email": email, "password": "senha-correta-123",
        })
        for _ in range(5):
            resp = client.post("/api/auth/login", json={"email": email, "password": "senha-errada"})
            assert resp.status_code == 401
        blocked = client.post("/api/auth/login", json={"email": email, "password": "senha-errada"})
        assert blocked.status_code == 429
        # Even the CORRECT password is blocked once rate-limited — the
        # whole point is to stop further guesses regardless of whether
        # this particular guess would have succeeded.
        still_blocked = client.post("/api/auth/login", json={"email": email, "password": "senha-correta-123"})
        assert still_blocked.status_code == 429
