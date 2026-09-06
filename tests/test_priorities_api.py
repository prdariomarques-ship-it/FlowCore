"""Tests for GET /api/priorities (Wealth Copilot MVP 2, phase 3)."""
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


class TestPrioritiesEndpoint:
    def test_returns_ranked_items(self):
        resp = _client().get("/api/priorities")
        assert resp.status_code == 200
        data = resp.json()
        for key in ("total", "by_level", "items", "available"):
            assert key in data
        assert data["total"] == len(data["items"])

    def test_never_returns_5xx_on_agent_failure(self):
        with patch("agents.priority_engine.PriorityEngine.run", side_effect=RuntimeError("boom")):
            resp = _client().get("/api/priorities")
        assert resp.status_code == 200
        assert resp.json()["available"] is False
