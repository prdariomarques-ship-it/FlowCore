"""Tests for GET /api/market (Wealth Copilot MVP 2, phase 1)."""
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


class TestMarketEndpoint:
    def test_returns_full_snapshot_shape(self):
        client = _client()
        resp = client.get("/api/market")
        assert resp.status_code == 200
        data = resp.json()
        for key in ("timestamp", "market_status", "movements", "relevant_changes",
                    "potential_impacts", "available"):
            assert key in data

    def test_movement_shape_matches_contract(self):
        items = {"watchlist": "default", "items": [
            {"symbol": "^GSPC", "level": 5271.0, "delta_pct_1d": 0.8, "status": "ok"},
        ]}
        with patch("runtime.market_intelligence.watchlist.snapshot", return_value=items):
            resp = _client().get("/api/market")
        sp500 = next(m for m in resp.json()["movements"] if m["asset"] == "S&P 500")
        assert sp500["current_value"] == 5271.0
        assert sp500["change"] == 0.8
        assert sp500["unit"] == "percent"
        assert sp500["relevance"] in ("HIGH", "MEDIUM", "LOW")

    def test_never_returns_5xx_on_agent_failure(self):
        with patch("agents.market_agent.MarketAgent.run", side_effect=RuntimeError("boom")):
            resp = _client().get("/api/market")
        assert resp.status_code == 200
        assert resp.json()["available"] is False
