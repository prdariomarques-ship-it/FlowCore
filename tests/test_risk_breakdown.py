"""Tests for runtime/portfolio/risk_breakdown.py — the dashboard's
"Risco da Carteira Agregada" donut (Wealth Copilot fase 7b, office-scoped
as of fase 0).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.portfolio.risk_breakdown import compute_risk_breakdown  # noqa: E402
from tests._auth_helper import signup_office  # noqa: E402

_PORTFOLIO = {
    "id": "test-1", "name": "Teste", "profile": "moderado",
    "target_allocation": [
        {"id": "rf1", "class": "renda_fixa_brasil", "weight": 40.0},
        {"id": "rf2", "class": "renda_fixa_internacional", "weight": 20.0},
        {"id": "rv1", "class": "renda_variavel_brasil", "weight": 15.0},
        {"id": "rv2", "class": "renda_variavel_global", "weight": 10.0},
        {"id": "mm1", "class": "multimercado", "weight": 10.0},
        {"id": "alt1", "class": "alternativos", "weight": 5.0},
    ],
    "current_allocation": None,
}


class TestFallsBackToTargetWhenNoCurrentPosition:
    def test_uses_target_weights_and_labels_source_honestly(self):
        # patch() auto-detects load_reference_portfolio is `async def` and
        # substitutes an AsyncMock, so `return_value` resolves correctly.
        with patch("runtime.portfolio.risk_breakdown.load_reference_portfolio", return_value=_PORTFOLIO):
            result = asyncio.run(compute_risk_breakdown("office-x"))
        assert result["source"] == "target_allocation"
        by_label = {c["label"]: c["weight"] for c in result["categories"]}
        assert by_label["Renda Fixa"] == 60.0
        assert by_label["Renda Variável"] == 25.0
        assert by_label["Multimercado"] == 10.0
        assert by_label["Alternativos"] == 5.0


class TestUsesCurrentAllocationWhenPresent:
    def test_sums_current_allocation_by_category(self):
        portfolio = {**_PORTFOLIO, "current_allocation": {
            "rf1": 30.0, "rf2": 20.0, "rv1": 20.0, "rv2": 15.0, "mm1": 10.0, "alt1": 5.0,
        }}
        with patch("runtime.portfolio.risk_breakdown.load_reference_portfolio", return_value=portfolio):
            result = asyncio.run(compute_risk_breakdown("office-x"))
        assert result["source"] == "current_allocation"
        by_label = {c["label"]: c["weight"] for c in result["categories"]}
        assert by_label["Renda Fixa"] == 50.0
        assert by_label["Renda Variável"] == 35.0


class TestNoPolicyDefined:
    def test_empty_target_allocation_reports_unavailable_not_zeroes(self):
        empty = {"id": "x", "name": "x", "profile": "", "target_allocation": [], "current_allocation": None}
        with patch("runtime.portfolio.risk_breakdown.load_reference_portfolio", return_value=empty):
            result = asyncio.run(compute_risk_breakdown("office-x"))
        assert result["source"] == "unavailable"
        assert result["categories"] == []


class TestCategoriesPartitionRealPortfolioWithoutDoubleCounting:
    def test_bundled_portfolio_categories_sum_to_100(self):
        # A freshly-seeded office gets the real bundled
        # config/portfolio_moderate_1m.json policy — confirms the four
        # categories are a genuine partition of the actual shipped
        # policy, not just the small test fixture above.
        client = _client()
        session = signup_office(client)
        result = asyncio.run(compute_risk_breakdown(session["office_id"]))
        total = sum(c["weight"] for c in result["categories"])
        assert abs(total - 100.0) < 0.01


def _client():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from api.router import create_app

    return TestClient(create_app(version="test"))


class TestRiskBreakdownEndpoint:
    def test_returns_categories_shape(self):
        client = _client()
        session = signup_office(client)
        resp = client.get("/api/portfolio/risk-breakdown", headers=session["headers"])
        assert resp.status_code == 200
        data = resp.json()
        for key in ("categories", "source", "profile", "available"):
            assert key in data

    def test_requires_auth(self):
        resp = _client().get("/api/portfolio/risk-breakdown")
        assert resp.status_code == 401

    def test_never_returns_5xx_on_failure(self):
        client = _client()
        session = signup_office(client)
        with patch("runtime.portfolio.risk_breakdown.compute_risk_breakdown", side_effect=RuntimeError("boom")):
            resp = client.get("/api/portfolio/risk-breakdown", headers=session["headers"])
        assert resp.status_code == 200
        assert resp.json()["available"] is False
