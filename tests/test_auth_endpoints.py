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
        resp = _client().post(
            "/api/auth/signup",
            json={
                "office_name": "Escritório",
                "name": "Teste",
                "email": _unique_email(),
                "password": "curta",
            },
        )
        assert resp.status_code == 422

    def test_password_longer_than_128_is_rejected(self):
        resp = _client().post(
            "/api/auth/signup",
            json={
                "office_name": "Escritório",
                "name": "Teste",
                "email": _unique_email(),
                "password": "a" * 129,
            },
        )
        assert resp.status_code == 422

    def test_password_at_minimum_length_is_accepted(self):
        resp = _client().post(
            "/api/auth/signup",
            json={
                "office_name": "Escritório",
                "name": "Teste",
                "email": _unique_email(),
                "password": "12345678",
            },
        )
        assert resp.status_code == 200

    def test_malformed_email_is_rejected(self):
        resp = _client().post(
            "/api/auth/signup",
            json={
                "office_name": "Escritório",
                "name": "Teste",
                "email": "not-an-email",
                "password": "senha-valida-123",
            },
        )
        assert resp.status_code == 422

    def test_duplicate_email_is_409(self):
        client = _client()
        email = _unique_email()
        first = client.post(
            "/api/auth/signup",
            json={
                "office_name": "A",
                "name": "A",
                "email": email,
                "password": "senha-valida-123",
            },
        )
        assert first.status_code == 200
        second = client.post(
            "/api/auth/signup",
            json={
                "office_name": "B",
                "name": "B",
                "email": email,
                "password": "outra-senha-456",
            },
        )
        assert second.status_code == 409

    def test_response_never_includes_password_fields(self):
        resp = _client().post(
            "/api/auth/signup",
            json={
                "office_name": "Escritório",
                "name": "Teste",
                "email": _unique_email(),
                "password": "senha-valida-123",
            },
        )
        body = resp.text.lower()
        assert "password_hash" not in body and "password_salt" not in body


class TestLoginAndLogout:
    def test_login_with_correct_password_succeeds(self):
        client = _client()
        email = _unique_email()
        client.post(
            "/api/auth/signup",
            json={
                "office_name": "Escritório",
                "name": "Teste",
                "email": email,
                "password": "senha-correta-123",
            },
        )
        resp = client.post("/api/auth/login", json={"email": email, "password": "senha-correta-123"})
        assert resp.status_code == 200
        assert resp.json()["token"]

    def test_login_with_wrong_password_is_401(self):
        client = _client()
        email = _unique_email()
        client.post(
            "/api/auth/signup",
            json={
                "office_name": "Escritório",
                "name": "Teste",
                "email": email,
                "password": "senha-correta-123",
            },
        )
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


class TestSessionsList:
    def test_requires_auth(self):
        assert _client().get("/api/auth/sessions").status_code == 401

    def test_lists_the_current_session_marked_as_current(self):
        client = _client()
        session = signup_office(client)
        resp = client.get("/api/auth/sessions", headers=session["headers"])
        assert resp.status_code == 200
        sessions = resp.json()["sessions"]
        assert len(sessions) == 1
        assert sessions[0]["current"] is True
        assert "token" not in sessions[0]

    def test_second_login_adds_a_third_session(self):
        # signup() itself already creates a session (the "keep me logged
        # in right after signing up" flow), so two logins on top of that
        # make three, not two.
        client = _client()
        email = _unique_email()
        client.post(
            "/api/auth/signup",
            json={
                "office_name": "Escritório",
                "name": "Teste",
                "email": email,
                "password": "senha-de-teste-123",
            },
        )
        client.post("/api/auth/login", json={"email": email, "password": "senha-de-teste-123"})
        login2 = client.post("/api/auth/login", json={"email": email, "password": "senha-de-teste-123"})
        headers2 = {"Authorization": f"Bearer {login2.json()['token']}"}

        sessions = client.get("/api/auth/sessions", headers=headers2).json()["sessions"]
        assert len(sessions) == 3
        # Exactly one is marked current -- the one whose token made this
        # very request -- never both, never neither.
        assert sum(1 for s in sessions if s["current"]) == 1

    def test_scoped_to_one_user(self):
        client = _client()
        signup_office(client)
        session_b = signup_office(client, "Outro Escritório")
        sessions_b = client.get("/api/auth/sessions", headers=session_b["headers"]).json()["sessions"]
        assert len(sessions_b) == 1


class TestSessionsDelete:
    def test_requires_auth(self):
        assert _client().delete("/api/auth/sessions/whatever").status_code == 401

    def test_unknown_session_id_is_404(self):
        client = _client()
        session = signup_office(client)
        resp = client.delete("/api/auth/sessions/does-not-exist", headers=session["headers"])
        assert resp.status_code == 404

    def test_revoking_a_session_logs_it_out(self):
        client = _client()
        email = _unique_email()
        client.post(
            "/api/auth/signup",
            json={
                "office_name": "Escritório",
                "name": "Teste",
                "email": email,
                "password": "senha-de-teste-123",
            },
        )
        login1 = client.post("/api/auth/login", json={"email": email, "password": "senha-de-teste-123"})
        login2 = client.post("/api/auth/login", json={"email": email, "password": "senha-de-teste-123"})
        headers1 = {"Authorization": f"Bearer {login1.json()['token']}"}
        headers2 = {"Authorization": f"Bearer {login2.json()['token']}"}

        session_id_1 = next(
            s["id"] for s in client.get("/api/auth/sessions", headers=headers1).json()["sessions"] if s["current"]
        )
        deleted = client.delete(f"/api/auth/sessions/{session_id_1}", headers=headers2)
        assert deleted.status_code == 200

        assert client.get("/api/auth/me", headers=headers1).status_code == 401
        assert client.get("/api/auth/me", headers=headers2).status_code == 200

    def test_cannot_delete_another_offices_session(self):
        client = _client()
        session_a = signup_office(client)
        session_b = signup_office(client, "Outro Escritório")
        session_id_a = client.get("/api/auth/sessions", headers=session_a["headers"]).json()["sessions"][0]["id"]

        resp = client.delete(f"/api/auth/sessions/{session_id_a}", headers=session_b["headers"])
        assert resp.status_code == 404
        # session_a's own session must still work -- session_b's attempt
        # was rejected, not silently accepted against the wrong user.
        assert client.get("/api/auth/me", headers=session_a["headers"]).status_code == 200


class TestLoginRateLimiting:
    def test_sixth_consecutive_failed_attempt_is_429(self):
        client = _client()
        email = _unique_email()
        client.post(
            "/api/auth/signup",
            json={
                "office_name": "Escritório",
                "name": "Teste",
                "email": email,
                "password": "senha-correta-123",
            },
        )
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
