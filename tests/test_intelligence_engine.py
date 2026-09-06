"""Tests for agents/intelligence_engine.py (Wealth Copilot MVP 2, phase 2).

All tests pass `market`/`compliance` in via context, matching the real
MarketSnapshot/ComplianceAgent output shapes, so none of this depends on
live yfinance access.
"""
from __future__ import annotations

import asyncio
import json

from agents.intelligence_engine import IntelligenceEngine, _AUDIT_LOG


def _run(coro):
    return asyncio.run(coro)


def _market(movements: list[dict] | None = None) -> dict:
    return {
        "timestamp": "2026-01-01T00:00:00+00:00", "market_status": "NORMAL",
        "movements": movements or [], "relevant_changes": [], "potential_impacts": [],
        "intelligence_events": [],
    }


def _movement(asset: str, change: float, relevance: str, unit: str = "percent") -> dict:
    return {
        "asset": asset, "previous_value": 100.0, "current_value": 100.0 + change,
        "change": change, "unit": unit, "relevance": relevance, "source": "live",
    }


def _compliance(portfolios: list[dict] | None = None) -> dict:
    return {"portfolios_evaluated": len(portfolios or []), "violations": [], "portfolios": portfolios or []}


def _violation(severity: str, type_: str = "EXCESSO_AI_THEME", client_id: str = "moderate-ia-1m") -> dict:
    return {
        "client_id": client_id, "client_name": "Carteira Moderada", "type": type_,
        "current": 16.0, "limit": 10.0, "diff": 6.0, "severity": severity,
        "message": f"Tema IA 6.0 p.p. acima do limite ({type_}).",
    }


class TestNeutral:
    def test_no_movements_no_violations_is_neutral(self):
        result = _run(IntelligenceEngine().run({"market": _market(), "compliance": _compliance()}))
        events = result["data"]["events"]
        assert len(events) == 1
        assert events[0]["status"] == "NEUTRAL"

    def test_low_relevance_movement_is_still_neutral(self):
        market = _market([_movement("Ibovespa", 0.1, "LOW")])
        result = _run(IntelligenceEngine().run({"market": market, "compliance": _compliance()}))
        assert result["data"]["events"][0]["status"] == "NEUTRAL"


class TestRecalibrate:
    def test_high_relevance_market_move_without_violation_is_recalibrate(self):
        market = _market([_movement("Ibovespa", -2.0, "HIGH")])
        result = _run(IntelligenceEngine().run({"market": market, "compliance": _compliance()}))
        events = result["data"]["events"]
        assert len(events) == 1
        assert events[0]["status"] == "RECALIBRATE"
        assert "suggested_action" in events[0]

    def test_us10y_high_move_names_duration_sensitive_assets(self):
        market = _market([_movement("US Treasury 10Y", 0.12, "HIGH", unit="percentage_points")])
        result = _run(IntelligenceEngine().run({"market": market, "compliance": _compliance()}))
        event = result["data"]["events"][0]
        assert event["status"] == "RECALIBRATE"
        assert "br_fixed_pre" in event["affected_assets"]
        assert event["suggested_action"] == "Reavaliar duration."

    def test_critical_violation_without_market_correlation_is_recalibrate_not_override(self):
        # A CRITICAL violation on its own (no HIGH us10y move behind it) is a
        # real problem, but not "a prior thesis was overturned by new
        # information" — that's the whole point of the OVERRIDE/RECALIBRATE
        # distinction the spec draws.
        compliance = _compliance([{"status": "DESENQUADRADO", "violations": [_violation("CRITICAL")]}])
        result = _run(IntelligenceEngine().run({"market": _market(), "compliance": compliance}))
        events = result["data"]["events"]
        assert len(events) == 1
        assert events[0]["status"] == "RECALIBRATE"

    def test_warning_violation_is_recalibrate(self):
        compliance = _compliance([{"status": "ATENCAO", "violations": [_violation("WARNING")]}])
        result = _run(IntelligenceEngine().run({"market": _market(), "compliance": compliance}))
        assert result["data"]["events"][0]["status"] == "RECALIBRATE"


class TestOverride:
    def test_critical_renda_fixa_violation_explained_by_us10y_is_override(self):
        market = _market([_movement("US Treasury 10Y", 0.15, "HIGH", unit="percentage_points")])
        compliance = _compliance([{
            "status": "DESENQUADRADO",
            "violations": [_violation("CRITICAL", type_="ABAIXO_RENDA_FIXA_TOTAL")],
        }])
        result = _run(IntelligenceEngine().run({"market": market, "compliance": compliance}))
        events = result["data"]["events"]
        override = next(e for e in events if e["status"] == "OVERRIDE")
        assert override["previous_thesis"]
        assert override["new_information"]
        assert override["impact"]
        assert override["affected_portfolios"] == ["moderate-ia-1m"]
        assert override["suggested_action"]

    def test_override_requires_both_high_move_and_matching_violation_type(self):
        # us10y HIGH alone (no renda-fixa violation) must NOT produce an
        # OVERRIDE — it should stay a RECALIBRATE market event.
        market = _market([_movement("US Treasury 10Y", 0.15, "HIGH", unit="percentage_points")])
        result = _run(IntelligenceEngine().run({"market": market, "compliance": _compliance()}))
        assert all(e["status"] != "OVERRIDE" for e in result["data"]["events"])


class TestAudit:
    def test_every_classification_is_written_to_the_audit_log(self):
        _AUDIT_LOG.unlink(missing_ok=True)
        market = _market([_movement("Ibovespa", -2.0, "HIGH")])
        _run(IntelligenceEngine().run({"market": market, "compliance": _compliance()}))
        assert _AUDIT_LOG.exists()
        lines = _AUDIT_LOG.read_text(encoding="utf-8").strip().splitlines()
        record = json.loads(lines[-1])
        for key in ("timestamp", "source", "input", "rule", "classification", "reason", "suggested_action"):
            assert key in record
        assert record["classification"] == "RECALIBRATE"


class TestAgentContract:
    def test_run_without_context_reads_real_market_and_compliance(self):
        result = _run(IntelligenceEngine().run())
        assert result["status"] == "ok"
        assert isinstance(result["data"]["events"], list)
        assert len(result["data"]["events"]) >= 1

    def test_health_check(self):
        health = _run(IntelligenceEngine().health_check())
        assert health["name"] == "intelligence"
        assert health["status"] == "ok"
