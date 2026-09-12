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

from runtime.portfolio.risk_breakdown import compute_model_risk_breakdown, compute_risk_breakdown  # noqa: E402
from tests._auth_helper import signup_office  # noqa: E402

_PORTFOLIO = {
    "id": "test-1",
    "name": "Teste",
    "profile": "moderado",
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
        assert by_label["Renda Fixa"] == 40.0
        assert by_label["Renda Variável"] == 15.0
        assert by_label["Internacional"] == 30.0
        assert by_label["Multimercado"] == 10.0
        assert by_label["Alternativos"] == 5.0


class TestUsesCurrentAllocationWhenPresent:
    def test_sums_current_allocation_by_category(self):
        portfolio = {
            **_PORTFOLIO,
            "current_allocation": {
                "rf1": 30.0,
                "rf2": 20.0,
                "rv1": 20.0,
                "rv2": 15.0,
                "mm1": 10.0,
                "alt1": 5.0,
            },
        }
        with patch("runtime.portfolio.risk_breakdown.load_reference_portfolio", return_value=portfolio):
            result = asyncio.run(compute_risk_breakdown("office-x"))
        assert result["source"] == "current_allocation"
        by_label = {c["label"]: c["weight"] for c in result["categories"]}
        assert by_label["Renda Fixa"] == 30.0
        assert by_label["Renda Variável"] == 20.0
        assert by_label["Internacional"] == 35.0


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


class TestModelPortfolios:
    """The firm's four static model risk profiles -- a comparison
    reference on the "Risco da Carteira Agregada" card, independent of
    any office's own live policy (see runtime/portfolio/model_portfolios.py)."""

    @pytest.mark.parametrize("profile", ["conservador", "moderado", "arrojado", "agressivo"])
    def test_every_profile_loads_and_sums_to_100(self, profile):
        result = compute_model_risk_breakdown(profile)
        assert result is not None
        assert result["profile"] == profile
        assert result["source"] == "target_allocation"  # never a fabricated "current position"
        total = sum(c["weight"] for c in result["categories"])
        assert abs(total - 100.0) < 0.1

    def test_unknown_profile_returns_none(self):
        assert compute_model_risk_breakdown("sofisticado") is None

    def test_risk_increases_from_conservador_to_agressivo(self):
        # Renda Variável + Internacional (the growth/volatility-bearing
        # slices) should monotonically increase across the risk ladder --
        # the whole point of having four distinct model profiles.
        def growth_pct(profile):
            r = compute_model_risk_breakdown(profile)
            by_label = {c["label"]: c["weight"] for c in r["categories"]}
            return by_label["Renda Variável"] + by_label["Internacional"]

        ladder = ["conservador", "moderado", "arrojado", "agressivo"]
        values = [growth_pct(p) for p in ladder]
        assert values == sorted(values)


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

    def test_profile_query_param_returns_the_model_policy_not_the_office_one(self):
        client = _client()
        session = signup_office(client)
        resp = client.get("/api/portfolio/risk-breakdown?profile=agressivo", headers=session["headers"])
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is True
        assert data["profile"] == "agressivo"
        assert data["source"] == "target_allocation"

    def test_arrojado_returns_its_own_distinct_weights_not_the_office_default(self):
        # Regression: the office's own uncustomized policy is seeded from
        # the SAME bundled moderado JSON as the "moderado" model profile,
        # so a bug that silently fell through to compute_risk_breakdown()
        # (the no-`profile` branch) instead of compute_model_risk_breakdown
        # would go unnoticed for "moderado" -- the numbers would coincide
        # -- but would visibly return the wrong (moderado) weights for
        # every other profile. "arrojado" is the case that actually
        # catches that class of bug.
        client = _client()
        session = signup_office(client)
        resp = client.get("/api/portfolio/risk-breakdown?profile=arrojado", headers=session["headers"])
        assert resp.status_code == 200
        data = resp.json()
        assert data["profile"] == "arrojado"
        by_label = {c["label"]: c["weight"] for c in data["categories"]}
        assert by_label["Renda Fixa"] == 12.0
        assert by_label["Renda Variável"] == 33.0
        assert by_label["Internacional"] == 30.0

    def test_unknown_profile_query_param_returns_404(self):
        client = _client()
        session = signup_office(client)
        resp = client.get("/api/portfolio/risk-breakdown?profile=sofisticado", headers=session["headers"])
        assert resp.status_code == 404

    def test_profile_query_param_requires_auth_too(self):
        resp = _client().get("/api/portfolio/risk-breakdown?profile=moderado")
        assert resp.status_code == 401


class TestModelProfilesEndpoint:
    def test_requires_auth(self):
        resp = _client().get("/api/portfolio/model-profiles")
        assert resp.status_code == 401

    def test_lists_all_four_profiles(self):
        client = _client()
        session = signup_office(client)
        resp = client.get("/api/portfolio/model-profiles", headers=session["headers"])
        assert resp.status_code == 200
        assert set(resp.json()["profiles"]) == {"conservador", "moderado", "arrojado", "agressivo"}
