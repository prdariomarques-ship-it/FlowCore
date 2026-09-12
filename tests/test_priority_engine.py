"""Tests for agents/priority_engine.py (Wealth Copilot MVP 2, phase 3)."""

from __future__ import annotations

import asyncio

import pytest

from agents.priority_engine import PriorityEngine


def _run(coro):
    return asyncio.run(coro)


def _event(status: str, reason: str = "x", affected_portfolios: list[str] | None = None) -> dict:
    return {
        "status": status,
        "reason": reason,
        "suggested_action": "Fazer algo.",
        "affected_portfolios": affected_portfolios or [],
    }


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


class TestGroupByClient:
    def test_market_only_events_are_excluded_from_by_client(self):
        result = _run(PriorityEngine().run({"events": [_event("RECALIBRATE")]}))
        assert result["data"]["by_client"] == []

    def test_groups_multiple_issues_for_the_same_client(self):
        events = [
            _event("OVERRIDE", reason="a", affected_portfolios=["p1"]),
            _event("RECALIBRATE", reason="b", affected_portfolios=["p1"]),
        ]
        result = _run(PriorityEngine().run({"events": events}))
        by_client = result["data"]["by_client"]
        assert len(by_client) == 1
        assert by_client[0]["client_id"] == "p1"
        assert by_client[0]["issues_count"] == 2

    def test_worst_level_is_the_clients_most_severe_issue(self):
        events = [
            _event("RECALIBRATE", reason="market-tied but not critical", affected_portfolios=["p1"]),  # HIGH
            _event("OVERRIDE", reason="thesis broken", affected_portfolios=["p1"]),  # CRITICAL
        ]
        result = _run(PriorityEngine().run({"events": events}))
        by_client = result["data"]["by_client"]
        assert by_client[0]["worst_level"] == "CRITICAL"
        assert by_client[0]["items"][0]["level"] == "CRITICAL"  # client's own items sorted too

    def test_clients_sorted_worst_first(self):
        events = [
            _event("RECALIBRATE", affected_portfolios=["p-medium-portfolio"]),  # HIGH (has affected_portfolios)
            _event("OVERRIDE", affected_portfolios=["p-critical"]),  # CRITICAL
        ]
        result = _run(PriorityEngine().run({"events": events}))
        client_ids = [c["client_id"] for c in result["data"]["by_client"]]
        assert client_ids == ["p-critical", "p-medium-portfolio"]

    def test_falls_back_to_client_id_when_no_office_id_to_resolve_a_real_name(self):
        result = _run(PriorityEngine().run({"events": [_event("OVERRIDE", affected_portfolios=["p1"])]}))
        assert result["data"]["by_client"][0]["client_name"] == "p1"
        assert result["data"]["by_client"][0]["is_demo"] is None

    def test_resolves_real_client_name_and_is_demo_flag_from_the_office(self):
        pytest.importorskip("fastapi")
        pytest.importorskip("httpx")
        from fastapi.testclient import TestClient

        from api.router import create_app
        from tests._auth_helper import seed_with_demo_clients, signup_office

        client = TestClient(create_app(version="test"))
        session = signup_office(client)
        seed_with_demo_clients(session["office_id"])
        demo_clients = client.get("/api/clients/demo", headers=session["headers"]).json()["clients"]
        target_id = next(c["id"] for c in demo_clients if c["id"] == "demo-client-21")  # Junqueira Capital, out of band

        result = _run(PriorityEngine().run({"office_id": session["office_id"]}))
        entry = next(c for c in result["data"]["by_client"] if c["client_id"] == target_id)
        assert entry["client_name"] == "Junqueira Capital"
        assert entry["is_demo"] is True

    def test_offices_own_reference_policy_is_never_a_by_client_card(self):
        """A violation's affected_portfolios can name the office's own
        policy (e.g. "moderate-ia-1m"), not a real client — that portfolio
        has no Client 360 to open and no one to contact, so it must never
        appear as a client card here (mirrors /api/alerts' is_client).
        Forces a real violation on the reference policy itself (ai_theme_max
        is 10.0 per config/portfolio_moderate_1m.json) so this actually
        exercises the filter instead of passing vacuously."""
        pytest.importorskip("fastapi")
        pytest.importorskip("httpx")
        from fastapi.testclient import TestClient

        from api.router import create_app
        from tests._auth_helper import signup_office

        client = TestClient(create_app(version="test"))
        session = signup_office(client)
        put_resp = client.put(
            "/api/portfolio/reference",
            json={"current_allocation": {"ai_theme": 20.0}},
            headers=session["headers"],
        )
        assert put_resp.status_code == 200

        result = _run(PriorityEngine().run({"office_id": session["office_id"]}))
        client_ids = [c["client_id"] for c in result["data"]["by_client"]]
        assert "moderate-ia-1m" not in client_ids
        # sanity: the violation really was produced (otherwise this test
        # would pass even without the filter)
        alerts_resp = client.get("/api/alerts", headers=session["headers"])
        assert any(v["client_id"] == "moderate-ia-1m" for v in alerts_resp.json()["items"])


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
