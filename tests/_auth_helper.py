"""Shared helper for tests that need an authenticated office session
against the live FastAPI TestClient (fase 0 multi-office auth).

Generates a fresh, globally-unique office/user per call (a random-suffix
email) so repeated test runs never collide with leftover data in the
shared dev database (data/flowcore.db) — the same tolerance-for-
accumulated-state approach this suite already uses elsewhere, since
there's no per-test isolated database at the API layer.

Only the very first office ever created on a given database gets the 27
seeded demo clients (see api/dashboard_routes.py's auth_signup) — that's
an inherently one-time bootstrap behavior, not something every test can
trigger. Tests that need a populated office should seed one explicitly
with seed_with_demo_clients() after signing up.
"""
from __future__ import annotations

import asyncio
import uuid


def signup_office(client, office_name: str = "Escritório de Teste") -> dict:
    """POST /api/auth/signup with a fresh, unique email. Returns
    {"token", "office_id", "user", "headers"} — `headers` is ready to
    pass as `headers=` to any TestClient call."""
    email = f"test-{uuid.uuid4().hex}@example.com"
    resp = client.post("/api/auth/signup", json={
        "office_name": office_name, "name": "Teste", "email": email, "password": "senha-de-teste-123",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    token = data["token"]
    return {
        "token": token, "office_id": data["office"]["id"], "user": data["user"],
        "headers": {"Authorization": f"Bearer {token}"},
    }


def seed_with_demo_clients(office_id: str) -> None:
    """Seed `office_id` with the 27 example clients — bypasses the
    "only the first office ever" bootstrap rule so any test can exercise
    the populated-office code paths deterministically."""
    from storage.client_repo import ClientRepository

    asyncio.run(ClientRepository().seed_office(office_id, with_demo_clients=True))
