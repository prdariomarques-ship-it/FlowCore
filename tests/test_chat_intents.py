"""Tests for the deterministic /api/ask chat intents added in Wealth
Copilot MVP2 phase 5 (market, intelligence, priority) — same pattern as
the existing compliance intercept: real agent data formatted as chat
prose instead of routed through an LLM.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.dashboard_routes import (  # noqa: E402
    _is_intelligence_question,
    _is_market_question,
    _is_priority_question,
)
from tests._auth_helper import signup_office  # noqa: E402


def _client():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from api.router import create_app

    return TestClient(create_app(version="test"))


def _client_and_headers():
    client = _client()
    return client, signup_office(client)["headers"]


class TestIntentDetection:
    def test_market_keywords(self):
        assert _is_market_question("o que aconteceu com o Ibovespa hoje?")
        assert _is_market_question("como está o dólar?")
        assert not _is_market_question("quais clientes estão desenquadrados?")

    def test_intelligence_keywords(self):
        assert _is_intelligence_question("explique esse override")
        assert _is_intelligence_question("por que essa carteira está em alerta?")
        assert not _is_intelligence_question("qual o preço do ouro?")

    def test_priority_keywords(self):
        assert _is_priority_question("o que devo priorizar hoje?")
        assert _is_priority_question("por onde começar?")
        assert not _is_priority_question("como está o mercado?")


class TestChatIntentsRequireAuth:
    def test_ask_requires_auth_for_agent_intents(self):
        resp = _client().post("/api/ask", json={"question": "como está o mercado?"})
        assert resp.status_code == 401


class TestMarketChatIntent:
    def test_reports_relevant_moves_with_mock_tag(self):
        client, headers = _client_and_headers()
        items = {"watchlist": "default", "items": [
            {"symbol": "^BVSP", "level": 130000.0, "delta_pct_1d": 3.2, "status": "ok"},
        ]}
        with patch("runtime.market_intelligence.watchlist.snapshot", return_value=items):
            resp = client.post("/api/ask", json={"question": "o que mudou no mercado hoje?"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "flowcore-market-agent"
        assert "Ibovespa" in data["answer"]
        assert "MOCK" in data["answer"]  # DI Jan always reports as MOCK

    def test_honest_when_no_data_available(self):
        client, headers = _client_and_headers()
        empty = {"watchlist": "default", "items": []}
        with patch("runtime.market_intelligence.watchlist.snapshot", return_value=empty):
            resp = client.post("/api/ask", json={"question": "como está o mercado?"}, headers=headers)
        answer = resp.json()["answer"]
        assert "DI Jan" not in answer or "MOCK" in answer  # DI mock is the only guaranteed item


class TestIntelligenceChatIntent:
    def test_neutral_when_no_events(self):
        client, headers = _client_and_headers()
        with patch("agents.intelligence_engine.IntelligenceEngine._market_events", return_value=[]), \
             patch("agents.intelligence_engine.IntelligenceEngine._compliance_events", return_value=[]):
            resp = client.post("/api/ask", json={"question": "explique esse override"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "flowcore-intelligence-engine"
        assert "estável" in data["answer"] or "Nenhum" in data["answer"]


class TestPriorityChatIntent:
    def test_reports_ranked_items_or_honest_empty_state(self):
        client, headers = _client_and_headers()
        resp = client.post("/api/ask", json={"question": "o que priorizar hoje?"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "flowcore-priority-engine"
        assert data["answer"]  # never empty — either a ranked list or the honest fallback


class TestChatIntentsNeverCrash:
    def test_market_never_returns_5xx_on_agent_failure(self):
        client, headers = _client_and_headers()
        with patch("agents.market_agent.MarketAgent.run", side_effect=RuntimeError("boom")):
            resp = client.post("/api/ask", json={"question": "como está o mercado?"}, headers=headers)
        assert resp.status_code == 200

    def test_intelligence_never_returns_5xx_on_agent_failure(self):
        client, headers = _client_and_headers()
        with patch("agents.intelligence_engine.IntelligenceEngine.run", side_effect=RuntimeError("boom")):
            resp = client.post("/api/ask", json={"question": "por que esse override?"}, headers=headers)
        assert resp.status_code == 200
        assert "não foi possível" in resp.json()["answer"].lower()
