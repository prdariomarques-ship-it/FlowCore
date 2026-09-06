"""Tests for agents/priority_engine.py (Wealth Copilot MVP 2, phase 3)."""
from __future__ import annotations

import asyncio

import pytest

from agents.priority_engine import PriorityEngine


def _run(coro):
    return asyncio.run(coro)


def _event(status: str, reason: str = "x", affected_portfolios: list[str] | None = None) -> dict:
    return {"status": status, "reason": reason, "suggested_action": "Fazer algo.",
            "affected_portfolios": affected_portfolios or []}


class TestLevelMapping:
    def test_override_is_critical(self):
        result = _run(PriorityEngine().run({"events": [_event("OVERRIDE")]}))
        assert result["data"]["items"][0]["level"] == "CRITICAL"

    def test_recalibrate_with_affected_portfolio_is_high(self):
        result = _run(PriorityEngine().run({"events": [_event("RECALIBRATE", affected_portfolios=["p1"])]}))
        assert result["data"]["items"][0]["level"] == "HIGH"

    def test_recalibrate_market_only_is_medium(self):
        result = _run(PriorityEngine().run({"events": [_event("RECALIBRATE")]}))
        assert result["data"]["items"][0]["level"] == "MEDIUM"

    def test_neutral_is_neutral(self):
        result = _run(PriorityEngine().run({"events": [_event("NEUTRAL")]}))
        assert result["data"]["items"][0]["level"] == "NEUTRAL"


class TestOrdering:
    def test_critical_events_come_before_lower_priority_ones(self):
        # Deliberately out of order on input.
        events = [
            _event("NEUTRAL"),
            _event("RECALIBRATE"),  # MEDIUM
            _event("OVERRIDE"),  # CRITICAL
            _event("RECALIBRATE", affected_portfolios=["p1"]),  # HIGH
        ]
        result = _run(PriorityEngine().run({"events": events}))
        levels = [i["level"] for i in result["data"]["items"]]
        assert levels == ["CRITICAL", "HIGH", "MEDIUM", "NEUTRAL"]

    def test_by_level_counts_match_items(self):
        events = [_event("OVERRIDE"), _event("OVERRIDE"), _event("NEUTRAL")]
        result = _run(PriorityEngine().run({"events": events}))
        assert result["data"]["by_level"]["CRITICAL"] == 2
        assert result["data"]["by_level"]["NEUTRAL"] == 1
        assert result["data"]["by_level"]["HIGH"] == 0


class TestClientsAffected:
    def test_affected_clients_count_matches_portfolio_list_length(self):
        result = _run(PriorityEngine().run({"events": [_event("OVERRIDE", affected_portfolios=["p1", "p2"])]}))
        assert result["data"]["items"][0]["affected_clients_count"] == 2


class TestAgentContract:
    def test_missing_office_id_raises_instead_of_a_silent_global_default(self):
        with pytest.raises(ValueError):
            _run(PriorityEngine().run())

    def test_office_id_computes_that_offices_real_priorities(self):
        pytest.importorskip("fastapi")
        pytest.importorskip("httpx")
        from fastapi.testclient import TestClient

        from api.router import create_app
        from tests._auth_helper import signup_office

        session = signup_office(TestClient(create_app(version="test")))
        result = _run(PriorityEngine().run({"office_id": session["office_id"]}))
        assert result["status"] == "ok"
        assert result["data"]["total"] >= 1

    def test_health_check(self):
        health = _run(PriorityEngine().health_check())
        assert health["name"] == "priority"
        assert health["status"] == "ok"
