"""Unit tests for POST /api/ask desenquadramento conversational queries."""

import pytest
from fastapi.testclient import TestClient
from api.router import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_ask_desenquadrado_query(client):
    response = client.post(
        "/api/ask",
        json={"question": "Quais clientes estão desenquadrados hoje?"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["provider"] == "compliance-agent"
    assert "carteira(s) com alertas" in data["answer"]
    assert "Junqueira Capital" in data["answer"] or "Nogueira Family Office" in data["answer"]
