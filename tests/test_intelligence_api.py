"""Tests for GET /api/intelligence (Wealth Copilot MVP 2, phase 2)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _client():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from api.router import create_app

    return TestClient(create_app(version="test"))


class TestIntelligenceEndpoint:
    def test_returns_counts_and_events(self):
        resp = _client().get("/api/intelligence")
        assert resp.status_code == 200
        data = resp.json()
        for key in ("total", "override", "recalibrate", "neutral", "events", "available"):
            assert key in data
        assert data["total"] == len(data["events"])

    def test_never_returns_5xx_on_agent_failure(self):
        with patch("agents.intelligence_engine.IntelligenceEngine.run", side_effect=RuntimeError("boom")):
            resp = _client().get("/api/intelligence")
        assert resp.status_code == 200
        assert resp.json()["available"] is False
