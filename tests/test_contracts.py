"""Tests for agents/contracts.py's IntelligenceEvent.to_dict() shape rules.

Covers the exact behavior agents/intelligence_engine.py depends on: which
fields appear for which status, and that RECALIBRATE's affected_assets/
affected_portfolios are optional (present only when non-empty) so a
generic RECALIBRATE keeps the spec's plain two-field example shape.
"""
from __future__ import annotations

from agents.contracts import IntelligenceEvent, MarketMovement


class TestIntelligenceEventShapes:
    def test_neutral_has_only_status_and_reason(self):
        event = IntelligenceEvent(status="NEUTRAL", reason="Sem mudança.")
        assert event.to_dict() == {"status": "NEUTRAL", "reason": "Sem mudança."}

    def test_recalibrate_without_affected_lists_omits_them(self):
        event = IntelligenceEvent(status="RECALIBRATE", reason="Curva abriu.", suggested_action="Reavaliar duration.")
        d = event.to_dict()
        assert d == {"status": "RECALIBRATE", "reason": "Curva abriu.", "suggested_action": "Reavaliar duration."}
        assert "affected_assets" not in d
        assert "affected_portfolios" not in d

    def test_recalibrate_with_affected_assets_includes_them(self):
        event = IntelligenceEvent(
            status="RECALIBRATE", reason="US10Y subiu.", suggested_action="Reavaliar duration.",
            affected_assets=["br_fixed_pre", "us_treasury"],
        )
        d = event.to_dict()
        assert d["affected_assets"] == ["br_fixed_pre", "us_treasury"]
        assert "affected_portfolios" not in d  # still omitted: it's empty

    def test_override_always_includes_all_its_fields_even_when_empty(self):
        event = IntelligenceEvent(status="OVERRIDE", reason="Premissa mudou.")
        d = event.to_dict()
        for key in ("previous_thesis", "new_information", "impact", "affected_assets",
                    "affected_portfolios", "suggested_action"):
            assert key in d


class TestMarketMovement:
    def test_to_dict_round_trips_all_fields(self):
        m = MarketMovement(asset="US10Y", previous_value=4.10, current_value=4.22, change=0.12,
                            unit="percentage_points", relevance="HIGH", source="live")
        d = m.to_dict()
        assert d["asset"] == "US10Y" and d["change"] == 0.12 and d["source"] == "live"
