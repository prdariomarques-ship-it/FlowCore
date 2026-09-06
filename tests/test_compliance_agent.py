"""Tests for agents/compliance_agent.py — the desenquadramento MVP.

Covers what was validated manually (not in a test file) when the agent
was first written: the honest "no data" states, real violation math
against portfolio_moderate_1m.json's actual sleeve_limits, and the
sleeve-level override added to avoid double-counting br_fixed_liquidity
inside renda_fixa_total.
"""
from __future__ import annotations

import asyncio

import pytest

from agents.compliance_agent import ComplianceAgent


def _run(coro):
    return asyncio.run(coro)


def _reference_portfolio(current_allocation: dict | None = None) -> dict:
    """The real bundled policy (id/target_allocation/sleeve_limits/
    review_policy), used directly via context["portfolios"] — these
    tests are about the sleeve-math logic, not the multi-office loading
    path (that has its own coverage in tests/test_client_repo.py), so
    they never need a real office_id/DB round-trip."""
    from storage.client_repo import _load_bundled_policy

    portfolio = _load_bundled_policy()
    portfolio["current_allocation"] = current_allocation
    return portfolio


class TestNoData:
    def test_reference_portfolio_without_position_reports_sem_posicao_atual(self):
        result = _run(ComplianceAgent().run({"portfolios": [_reference_portfolio(None)]}))
        data = result["data"]
        assert data["violations"] == []
        assert data["portfolios"][0]["status"] == "SEM_POSICAO_ATUAL"

    def test_portfolio_without_policy_reports_sem_regras_definidas(self):
        portfolio = {"id": "real-1", "name": "Corretora XP", "target_allocation": [], "_no_policy": True}
        result = _run(ComplianceAgent().run({"portfolios": [portfolio]}))
        data = result["data"]
        assert data["violations"] == []
        assert data["portfolios"][0]["status"] == "SEM_REGRAS_DEFINIDAS"

    def test_missing_office_id_and_no_portfolios_raises_instead_of_a_silent_global_default(self):
        """Fase 0 (multi-office): there is no longer a single installation-
        wide default to silently fall back to — an office_id is mandatory
        whenever `portfolios` isn't precomputed, or one office's alerts
        could accidentally return another's data."""
        with pytest.raises(ValueError):
            _run(ComplianceAgent().run())

    def test_office_id_loads_that_offices_real_registered_state(self, tmp_path):
        from unittest.mock import patch

        from storage.client_repo import ClientRepository

        repo = ClientRepository(db_path=str(tmp_path / "t.db"))

        async def scenario():
            await repo.seed_office("office-1", with_demo_clients=True)
            return await ComplianceAgent().run({"office_id": "office-1"})

        with patch("runtime.portfolio.reference.ClientRepository", return_value=repo), \
             patch("runtime.portfolio.demo_clients.ClientRepository", return_value=repo):
            result = _run(scenario())
        assert result["status"] == "ok"
        assert result["data"]["portfolios_evaluated"] == 28  # 1 policy row + 27 demo clients


class TestViolations:
    def test_excess_ai_theme_is_detected_against_the_real_limit(self):
        # sleeve_limits.ai_theme_max = 10.0 in portfolio_moderate_1m.json
        portfolio = _reference_portfolio({"ai_theme": 16.0})
        result = _run(ComplianceAgent().run({"portfolios": [portfolio]}))
        violations = result["data"]["violations"]
        ai_violations = [v for v in violations if v["type"] == "EXCESSO_AI_THEME"]
        assert len(ai_violations) == 1
        v = ai_violations[0]
        assert v["current"] == 16.0
        assert v["limit"] == 10.0
        assert v["diff"] == 6.0

    def test_warning_vs_critical_severity_threshold(self):
        # limit=10, default critical_margin=5 -> +2 over limit is WARNING, +8 is CRITICAL.
        # Every other sleeve is left within its band so only ai_theme fires —
        # a portfolio with unrelated sleeves left at 0 would also breach
        # renda_fixa_total/liquidity and make violations[0] positional
        # (caught by this test's first version: a bug in the test, not the
        # agent — filtering by type is what actually makes this reliable).
        base = {"__sleeve__:renda_fixa_total": 60.0, "__sleeve__:alternativos": 4.5, "br_fixed_liquidity": 10.0}

        def ai_theme_violation(ai_theme_weight: float) -> dict:
            portfolio = _reference_portfolio({**base, "ai_theme": ai_theme_weight})
            result = _run(ComplianceAgent().run({"portfolios": [portfolio]}))
            matches = [v for v in result["data"]["violations"] if v["type"] == "EXCESSO_AI_THEME"]
            assert len(matches) == 1
            return matches[0]

        assert ai_theme_violation(12.0)["severity"] == "WARNING"
        assert ai_theme_violation(18.0)["severity"] == "CRITICAL"

    def test_no_violation_when_within_limits(self):
        # A position that sits inside every sleeve_limits band should
        # produce zero violations and status NORMAL.
        portfolio = _reference_portfolio({
            "__sleeve__:renda_fixa_total": 60.0,
            "ai_theme": 7.0,
            "__sleeve__:alternativos": 4.5,
            "br_fixed_liquidity": 10.0,
        })
        result = _run(ComplianceAgent().run({"portfolios": [portfolio]}))
        assert result["data"]["violations"] == []
        assert result["data"]["portfolios"][0]["status"] == "NORMAL"


class TestSleeveOverride:
    """br_fixed_liquidity belongs to class renda_fixa_brasil (rolls up
    into renda_fixa_total) AND is the item the liquidity floor checks.
    Without the __sleeve__ override, setting both independently would
    double-count it inside renda_fixa_total."""

    def test_item_level_current_allocation_sums_into_the_sleeve(self):
        # renda_fixa_total = renda_fixa_brasil + renda_fixa_internacional items.
        # Put the whole 60% on a single constituent item (br_fixed_post) —
        # the sleeve check should see it as the sleeve's current weight.
        portfolio = _reference_portfolio({"br_fixed_post": 60.0})
        result = _run(ComplianceAgent().run({"portfolios": [portfolio]}))
        rf_violations = [v for v in result["data"]["violations"] if "RENDA_FIXA_TOTAL" in v["type"]]
        # 60.0 is within [55, 65] -> no violation, but liquidity floor (10.0)
        # is unmet (br_fixed_liquidity defaults to 0 here) -> that fires.
        assert not rf_violations
        assert any(v["type"] == "ABAIXO_LIQUIDEZ" for v in result["data"]["violations"])

    def test_sleeve_override_prevents_double_counting_liquidity(self):
        # Without the override: setting br_fixed_liquidity=10 (to satisfy
        # the liquidity floor) would ALSO add +10 into renda_fixa_total's
        # item-level sum. With the override, renda_fixa_total is read
        # directly from the synthetic key and liquidity's own value has no
        # side effect on it.
        portfolio = _reference_portfolio({
            "__sleeve__:renda_fixa_total": 60.0,
            "br_fixed_liquidity": 10.0,
        })
        result = _run(ComplianceAgent().run({"portfolios": [portfolio]}))
        violations = result["data"]["violations"]
        assert not any("RENDA_FIXA_TOTAL" in v["type"] for v in violations)
        assert not any(v["type"] == "ABAIXO_LIQUIDEZ" for v in violations)

    def test_without_override_item_level_liquidity_leaks_into_the_sleeve_sum(self):
        # Documents the exact failure mode the override exists to prevent:
        # same inputs as above but WITHOUT the synthetic key, the item-level
        # sum for renda_fixa_total only sees br_fixed_liquidity=10 (the only
        # renda_fixa item set) -> far short of the 55 floor -> a violation
        # fires that the override-based test above correctly avoids.
        portfolio = _reference_portfolio({"br_fixed_liquidity": 10.0})
        result = _run(ComplianceAgent().run({"portfolios": [portfolio]}))
        violations = result["data"]["violations"]
        assert any(v["type"] == "ABAIXO_RENDA_FIXA_TOTAL" for v in violations)


class TestAgentContract:
    def test_run_returns_status_and_data_keys(self):
        result = _run(ComplianceAgent().run({"portfolios": []}))
        assert result["status"] == "ok"
        assert "violations" in result["data"]
        assert "portfolios" in result["data"]

    def test_health_check(self):
        health = _run(ComplianceAgent().health_check())
        assert health["name"] == "compliance"
        assert health["status"] == "ok"
