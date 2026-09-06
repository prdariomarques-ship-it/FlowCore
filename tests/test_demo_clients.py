"""Tests for the 27 example client records (Wealth Copilot fase 9) —
explicitly fictitious, explicitly editable seed data used to populate
the multi-client dashboard views until FlowCore has a real multi-client
integration. See runtime/portfolio/demo_clients.py for why this is a
different category from "never fabricate data": it's deliberately
created, clearly labeled (demo=True everywhere), fully editable/
replaceable placeholder data, the same as the reference/model portfolio.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.portfolio.demo_clients import (  # noqa: E402
    load_demo_clients,
    reset_demo_clients,
    save_demo_client,
)


@pytest.fixture(autouse=True)
def _clean_runtime_copy():
    reset_demo_clients()
    yield
    reset_demo_clients()


class TestBundledDefaults:
    def test_exactly_27_clients(self):
        assert len(load_demo_clients()) == 27

    def test_every_client_is_flagged_demo(self):
        assert all(c.get("demo") is True for c in load_demo_clients())

    def test_every_client_has_a_name_and_current_allocation(self):
        for c in load_demo_clients():
            assert c.get("name")
            assert c.get("current_allocation")


class TestEditing:
    def test_save_merges_onto_existing_position(self):
        clients = load_demo_clients()
        client_id = clients[0]["id"]
        updated = save_demo_client(client_id, {"ai_theme": 9.0})
        assert updated["current_allocation"]["ai_theme"] == 9.0
        # Other fields on that client's position untouched.
        assert "__sleeve__:renda_fixa_total" in updated["current_allocation"]

    def test_save_persists_across_reloads(self):
        client_id = load_demo_clients()[0]["id"]
        save_demo_client(client_id, {"ai_theme": 3.3})
        reloaded = next(c for c in load_demo_clients() if c["id"] == client_id)
        assert reloaded["current_allocation"]["ai_theme"] == 3.3

    def test_unknown_client_id_raises(self):
        with pytest.raises(KeyError):
            save_demo_client("does-not-exist", {"ai_theme": 1.0})

    def test_reset_discards_edits(self):
        client_id = load_demo_clients()[0]["id"]
        original = next(c for c in load_demo_clients() if c["id"] == client_id)["current_allocation"]["ai_theme"]
        save_demo_client(client_id, {"ai_theme": original + 50})
        reset_demo_clients()
        reloaded = next(c for c in load_demo_clients() if c["id"] == client_id)
        assert reloaded["current_allocation"]["ai_theme"] == original


class TestComplianceAgentIntegration:
    def test_demo_clients_are_evaluated_and_flagged(self):
        from agents.compliance_agent import ComplianceAgent
        import asyncio

        result = asyncio.run(ComplianceAgent().run())
        portfolios = result["data"]["portfolios"]
        demo_portfolios = [p for p in portfolios if p.get("is_demo")]
        assert len(demo_portfolios) == 27
        # At least one of the deliberately-out-of-band demo clients
        # produces a real violation, and that violation is itself
        # flagged is_demo so the alerts table can label it "exemplo".
        violations = result["data"]["violations"]
        demo_violations = [v for v in violations if v.get("is_demo")]
        assert demo_violations

    def test_reference_portfolio_is_not_flagged_demo(self):
        from agents.compliance_agent import ComplianceAgent
        import asyncio

        result = asyncio.run(ComplianceAgent().run())
        reference = next(p for p in result["data"]["portfolios"] if p["portfolio_id"] == "moderate-ia-1m")
        assert reference.get("is_demo") is False


def _client():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from api.router import create_app

    return TestClient(create_app(version="test"))


class TestDemoClientsEndpoints:
    def test_list_returns_27(self):
        resp = _client().get("/api/clients/demo")
        assert resp.status_code == 200
        assert len(resp.json()["clients"]) == 27

    def test_update_unknown_client_is_404(self):
        resp = _client().put("/api/clients/demo/nope", json={"current_allocation": {"ai_theme": 1.0}})
        assert resp.status_code == 404

    def test_update_and_reset_roundtrip(self):
        client_id = load_demo_clients()[0]["id"]
        put_resp = _client().put(f"/api/clients/demo/{client_id}", json={"current_allocation": {"ai_theme": 2.0}})
        assert put_resp.status_code == 200
        assert put_resp.json()["client"]["current_allocation"]["ai_theme"] == 2.0

        reset_resp = _client().post("/api/clients/demo/reset")
        assert reset_resp.status_code == 200

    def test_alerts_endpoint_includes_demo_flag(self):
        resp = _client().get("/api/alerts")
        data = resp.json()
        assert any("is_demo" in item for item in data["items"]) or data["items"] == []
