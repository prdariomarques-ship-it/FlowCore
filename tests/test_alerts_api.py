"""Integration tests for GET /api/alerts endpoint."""

import pytest
from fastapi.testclient import TestClient
from api.router import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_get_alerts_endpoint(client):
    response = client.get("/api/alerts")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert "total" in data
    assert "critical" in data
    assert "warnings" in data
    assert "items" in data
    assert isinstance(data["items"], list)
    assert len(data["items"]) == data["total"]

    if data["total"] > 0:
        item = data["items"][0]
        assert "client_id" in item
        assert "client_name" in item
        assert "type" in item
        assert "current" in item
        assert "limit" in item
        assert "diff" in item
        assert "severity" in item
        assert "message" in item
