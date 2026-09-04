"""Tests for runtime.decision.engine.DecisionEngine (Sprint 24).

Core tier — ImpactEngine is mocked (its own coverage lives in
tests/impact/), so these tests exercise DecisionEngine's own
materiality/scoring/ranking/product-enrichment orchestration in
isolation. Async calls driven via asyncio.run(), matching the
convention already established in tests/impact/test_engine.py.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _driver(
    dimension, direction="negative", regime="elevated", exposed_weight_pct=40.0, regime_score=2.5, confidence_score=0.9
):
    from runtime.impact.models import DriverImpact

    return DriverImpact(
        dimension=dimension,
        driver=f"driver-{dimension}",
        regime=regime,
        regime_score=regime_score if regime != "insufficient_data" else None,
        direction=direction,
        expected_impact="strong" if exposed_weight_pct >= 40 else "mild",
        confidence_score=confidence_score if regime != "insufficient_data" else 0.0,
        confidence_label="high",
        exposed_weight_pct=exposed_weight_pct,
        positive_weight_pct=exposed_weight_pct if direction == "positive" else 0.0,
        negative_weight_pct=exposed_weight_pct if direction == "negative" else 0.0,
        reason=f"reason for {dimension}",
        affected_symbols=["AAPL"],
    )


def _recommendation(dimension, action_key="reduce_duration"):
    from runtime.impact.models import Recommendation

    return Recommendation(
        action_key=action_key,
        action=f"action for {dimension}",
        reason="r",
        confidence=0.9,
        affected_holdings=["AAPL"],
        dimension=dimension,
    )


def _concentration_recommendation():
    from runtime.impact.models import Recommendation

    return Recommendation(
        action_key="reduce_concentration",
        action="Reduzir concentracao",
        reason="HHI alto",
        confidence=0.7,
        affected_holdings=["AAPL", "XOM"],
        dimension="",
    )


def _impact_report(drivers, recommendations, opportunities, unvalued_count=0):
    from runtime.impact.models import ImpactReport

    return ImpactReport(
        portfolio_id=1,
        overall_impact="negative" if recommendations else "neutral",
        confidence=0.5,
        portfolio_risk_score=30.0,
        drivers=drivers,
        affected_dimensions=[d.dimension for d in drivers if d.direction != "neutral"],
        recommendations=recommendations,
        opportunities=opportunities,
        unvalued_count=unvalued_count,
    )


def _fake_impact_engine(report):
    engine = AsyncMock()
    engine.compute.return_value = report
    return engine


class TestComputeBasics:
    def test_material_negative_driver_becomes_a_risk_decision(self):
        from runtime.decision.engine import DecisionEngine
        from runtime.exposure import ExposureEngine

        driver = _driver("risk_sentiment", direction="negative", exposed_weight_pct=40.0)
        rec = _recommendation("risk_sentiment", action_key="increase_usd_liquidity")
        report = _impact_report([driver], [rec], [])
        engine = DecisionEngine(_fake_impact_engine(report), ExposureEngine())

        decision_report = asyncio.run(engine.compute(1, [{"symbol": "AAPL", "market_value": 1000.0, "asset": {}}]))

        assert len(decision_report.decisions) == 1
        d = decision_report.decisions[0]
        assert d.id == "increase_usd_liquidity"
        assert d.kind == "risk"
        assert d.priority == 1
        assert decision_report.overall_priority == d.urgency
        assert d.action == "action for risk_sentiment"
        assert len(d.reason_chain) == 8

    def test_material_positive_driver_becomes_an_opportunity_decision(self):
        from runtime.decision.engine import DecisionEngine
        from runtime.exposure import ExposureEngine

        driver = _driver("commodities", direction="positive", exposed_weight_pct=40.0)
        rec = _recommendation("commodities", action_key="increase_commodities_exposure")
        report = _impact_report([driver], [], [rec])
        engine = DecisionEngine(_fake_impact_engine(report), ExposureEngine())

        decision_report = asyncio.run(engine.compute(1, [{"symbol": "GLD", "market_value": 1000.0, "asset": {}}]))

        assert len(decision_report.decisions) == 1
        assert decision_report.decisions[0].kind == "opportunity"
        assert decision_report.top_opportunities == ["action for commodities"]
        assert decision_report.top_risks == []

    def test_immaterial_driver_produces_no_decision(self):
        """Below MIN_EXPOSED_WEIGHT_PCT -- Layer 3 might still have
        emitted a Recommendation (exposed_weight_pct > 0 is enough for
        that), but the Decision Engine's stricter gate excludes it."""
        from runtime.decision.engine import DecisionEngine
        from runtime.exposure import ExposureEngine

        driver = _driver("risk_sentiment", direction="negative", exposed_weight_pct=2.0)
        rec = _recommendation("risk_sentiment")
        report = _impact_report([driver], [rec], [])
        engine = DecisionEngine(_fake_impact_engine(report), ExposureEngine())

        decision_report = asyncio.run(engine.compute(1, [{"symbol": "AAPL", "market_value": 1000.0, "asset": {}}]))
        assert decision_report.decisions == []
        assert decision_report.overall_priority == "NONE"

    def test_concentration_recommendation_becomes_a_structural_decision(self):
        from runtime.decision.engine import DecisionEngine
        from runtime.exposure import ExposureEngine

        report = _impact_report([], [_concentration_recommendation()], [])
        holdings = [
            {"symbol": "AAPL", "market_value": 800.0, "asset": {}},
            {"symbol": "XOM", "market_value": 200.0, "asset": {}},
        ]
        engine = DecisionEngine(_fake_impact_engine(report), ExposureEngine())

        decision_report = asyncio.run(engine.compute(1, holdings))
        assert len(decision_report.decisions) == 1
        d = decision_report.decisions[0]
        assert d.id == "reduce_concentration"
        assert d.dimension == ""
        assert d.kind == "risk"

    def test_multiple_decisions_ranked_by_priority_score(self):
        from runtime.decision.engine import DecisionEngine
        from runtime.exposure import ExposureEngine

        weak_driver = _driver(
            "commodities", direction="positive", exposed_weight_pct=8.0, regime_score=1.1, confidence_score=0.55
        )
        strong_driver = _driver(
            "risk_sentiment", direction="negative", exposed_weight_pct=80.0, regime_score=4.0, confidence_score=0.95
        )
        report = _impact_report(
            [weak_driver, strong_driver],
            [_recommendation("risk_sentiment", "increase_usd_liquidity")],
            [_recommendation("commodities", "increase_commodities_exposure")],
        )
        engine = DecisionEngine(_fake_impact_engine(report), ExposureEngine())

        decision_report = asyncio.run(engine.compute(1, [{"symbol": "AAPL", "market_value": 1000.0, "asset": {}}]))
        assert decision_report.decisions[0].id == "increase_usd_liquidity"
        assert decision_report.decisions[0].priority == 1
        assert decision_report.decisions[1].priority == 2

    def test_recommended_products_reuse_product_mapping_layer(self):
        from runtime.decision.engine import DecisionEngine
        from runtime.exposure import ExposureEngine

        driver = _driver("liquidity", direction="negative", exposed_weight_pct=40.0)
        rec = _recommendation("liquidity", action_key="reduce_duration")
        report = _impact_report([driver], [rec], [])
        engine = DecisionEngine(_fake_impact_engine(report), ExposureEngine())

        decision_report = asyncio.run(
            engine.compute(1, [{"symbol": "AAPL", "market_value": 1000.0, "asset": {}}], shelf="us_etf")
        )
        products = decision_report.decisions[0].recommended_products
        assert len(products) > 0
        assert all("symbol" in p and "name" in p for p in products)


class TestEdgeCases:
    def test_empty_portfolio(self):
        from runtime.decision.engine import DecisionEngine
        from runtime.exposure import ExposureEngine

        report = _impact_report([], [], [])
        engine = DecisionEngine(_fake_impact_engine(report), ExposureEngine())

        decision_report = asyncio.run(engine.compute(1, []))
        assert decision_report.decisions == []
        assert decision_report.overall_priority == "NONE"
        assert decision_report.overall_confidence == 0.0
        # macro_alignment is always computable from portfolio_risk_score
        # alone, so the overall score isn't insufficient_data just
        # because holdings are empty -- but every holdings-dependent
        # sub-score correctly is.
        assert decision_report.portfolio_score.overall_status == "computed"
        by_name = {s.name: s for s in decision_report.portfolio_score.sub_scores}
        assert by_name["concentration"].status == "insufficient_data"
        assert by_name["diversification"].status == "insufficient_data"

    def test_all_insufficient_data_regimes(self):
        from runtime.decision.engine import DecisionEngine
        from runtime.exposure import ExposureEngine

        drivers = [_driver(dim, regime="insufficient_data") for dim in ("liquidity", "commodities", "risk_sentiment")]
        report = _impact_report(drivers, [], [])
        engine = DecisionEngine(_fake_impact_engine(report), ExposureEngine())

        decision_report = asyncio.run(engine.compute(1, [{"symbol": "AAPL", "market_value": 1000.0, "asset": {}}]))
        assert decision_report.decisions == []

    def test_missing_prices_counted_but_no_crash(self):
        from runtime.decision.engine import DecisionEngine
        from runtime.exposure import ExposureEngine

        report = _impact_report([], [], [], unvalued_count=2)
        engine = DecisionEngine(_fake_impact_engine(report), ExposureEngine())

        decision_report = asyncio.run(engine.compute(1, [{"symbol": "AAPL", "market_value": None, "asset": {}}]))
        assert decision_report.unvalued_count == 2

    def test_recommendation_referencing_a_dimension_with_no_matching_driver_is_skipped(self):
        """Defensive edge case: a Recommendation whose `dimension` isn't
        present in ImpactReport.drivers (shouldn't happen given how
        ImpactEngine builds both together, but the Decision Engine must
        not crash if it ever does)."""
        from runtime.decision.engine import DecisionEngine
        from runtime.exposure import ExposureEngine

        rec = _recommendation("unknown_dimension")
        report = _impact_report([], [rec], [])
        engine = DecisionEngine(_fake_impact_engine(report), ExposureEngine())

        decision_report = asyncio.run(engine.compute(1, [{"symbol": "AAPL", "market_value": 1000.0, "asset": {}}]))
        assert decision_report.decisions == []
