"""Integration test for conversational ask compliance queries."""

import pytest
from starlette.testclient import TestClient
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
    assert "Maria Oliveira" in data["answer"]
