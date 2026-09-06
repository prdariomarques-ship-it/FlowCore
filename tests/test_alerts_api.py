"""Tests for /api/alerts and compliance conversational chat in api/router.py."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("starlette")
pytest.importorskip("httpx")

from starlette.testclient import TestClient
from api.router import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_get_alerts_endpoint(client):
    res = client.get("/api/alerts")
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "critical" in data
    assert "warnings" in data
    assert "items" in data
    assert isinstance(data["items"], list)


def test_ask_compliance_queries(client):
    res = client.post("/api/ask", json={"question": "Quais clientes estão desenquadrados?"})
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert data["provider"] == "compliance-agent"
    assert data["model"] == "rule-engine"
