"""Tests for the FlowCore API & Web UI endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from api.router import create_app

@pytest.fixture
def client():
    app = create_app(version="4.0.0", platform_info={"host": "android"})
    return TestClient(app)

def test_get_root_ui(client):
    """Verify that GET / returns the Web UI HTML template."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "FlowCore | Professional Platform Environment" in response.text
    assert "System Dashboard" in response.text
    assert "Interactive AI Assistant" in response.text

def test_api_health(client):
    """Verify the /api/health endpoint."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "4.0.0"
    assert "platform" in data

def test_api_config_get_and_post(client):
    """Verify GET and POST on /api/config."""
    # Get current config
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert data["model"] == "qwen2.5:7b"

    # Post new config
    payload = {
        "model": "glm4:9b",
        "platform": "macOS",
        "prefix": "/usr/local",
        "home": "/home/jules",
        "log_level": "DEBUG"
    }
    post_response = client.post("/api/config", json=payload)
    assert post_response.status_code == 200
    assert post_response.json()["status"] == "success"

    # Get config again to verify update
    response2 = client.get("/api/config")
    assert response2.json()["model"] == "glm4:9b"
    assert response2.json()["platform"] == "macOS"

def test_api_chat(client):
    """Verify POST /api/chat capability intention routing."""
    # Test general query
    response = client.post("/api/chat", json={"message": "Como vai?"})
    assert response.status_code == 200
    assert "como vai?" in response.json()["response"].lower() or "recebi" in response.json()["response"].lower()

    # Test battery query (fallback or real)
    response_battery = client.post("/api/chat", json={"message": "bateria"})
    assert response_battery.status_code == 200
    assert "battery" in response_battery.json()["response"].lower() or "bateria" in response_battery.json()["response"].lower()

    # Test wifi query (fallback or real)
    response_wifi = client.post("/api/chat", json={"message": "wifi"})
    assert response_wifi.status_code == 200
    assert "wi-fi" in response_wifi.json()["response"].lower() or "wifi" in response_wifi.json()["response"].lower()

def test_api_doctor(client):
    """Verify GET /api/doctor system diagnostics."""
    response = client.get("/api/doctor")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "checks" in data
    assert any(check["name"] == "Python Environment" for check in data["checks"])
