"""Tests for Agent APIs (agent-runs, ai-costs, approvals, events)."""

import pytest
from fastapi.testclient import TestClient
from api.router import create_app

client = TestClient(create_app())

def test_api_agent_runs():
    resp = client.get("/api/agent-runs")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "runs" in data

def test_api_ai_costs():
    resp = client.get("/api/ai-costs")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_cost_usd" in data

def test_api_approvals():
    resp = client.get("/api/approvals")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data

def test_api_publish_event():
    resp = client.post("/api/events", json={
        "event_type": "CLIENT_WITHDRAWAL",
        "entity": "cli_999",
        "payload": {"amount": 500000.0},
        "priority": "HIGH"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "PUBLISHED"
    assert data["event"]["entity"] == "cli_999"
