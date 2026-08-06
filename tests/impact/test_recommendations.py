"""Tests for runtime.impact.recommendations (Sprint 23).

Core tier — pure computation, no network.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _driver(dimension, direction, exposed_weight_pct=50.0, confidence_score=0.8, symbols=None, asset_classes=None):
    from runtime.impact.models import DriverImpact

    return DriverImpact(
        dimension=dimension,
        driver=f"driver-{dimension}",
        regime="elevated",
        regime_score=2.0,
        direction=direction,
        expected_impact="moderate",
        confidence_score=confidence_score,
        confidence_label="high",
        exposed_weight_pct=exposed_weight_pct,
        positive_weight_pct=exposed_weight_pct if direction == "positive" else 0.0,
        negative_weight_pct=exposed_weight_pct if direction == "negative" else 0.0,
        reason=f"reason for {dimension}",
        affected_symbols=symbols or [],
        affected_asset_classes=asset_classes or [],
    )


def _concentration(hhi=1000.0, holding_count=3, top_holding_weight_pct=40.0, top_5_weight_pct=100.0):
    from runtime.exposure import ConcentrationReport

    return ConcentrationReport(
        total_market_value=1000.0,
        top_holding_weight_pct=top_holding_weight_pct,
        top_5_weight_pct=top_5_weight_pct,
        hhi=hhi,
        holding_count=holding_count,
        unvalued_count=0,
        computed_at="t",
    )


class TestBuildRecommendations:
    def test_negative_driver_produces_recommendation(self):
        from runtime.impact.recommendations import build_recommendations

        drivers = [_driver("liquidity", "negative", symbols=["AAPL"], asset_classes=["equity"])]
        recs = build_recommendations([], drivers, _concentration())
        assert len(recs) == 1
        assert recs[0].affected_holdings == ["AAPL"]
        assert recs[0].affected_asset_classes == ["equity"]
        assert recs[0].confidence == 0.8
        assert recs[0].action_key == "reduce_duration"
        assert "duracao" in recs[0].action.lower() or "caixa" in recs[0].action.lower()

    def test_action_key_is_never_a_product_name(self):
        """Architectural boundary: action_key is always the generic,
        stable slug consumed by runtime/product_mapping/ -- never a
        ticker. Loosely checked here (no uppercase-heavy short tokens
        typical of tickers) as a regression tripwire."""
        from runtime.impact.recommendations import build_opportunities, build_recommendations

        drivers = [
            _driver("liquidity", "negative"),
            _driver("commodities", "positive"),
            _driver("risk_sentiment", "negative"),
        ]
        recs = build_recommendations([], drivers, _concentration())
        opps = build_opportunities(drivers)
        for item in recs + opps:
            assert item.action_key.islower()
            assert " " not in item.action_key

    def test_positive_driver_does_not_produce_a_recommendation(self):
        from runtime.impact.recommendations import build_recommendations

        drivers = [_driver("liquidity", "positive")]
        recs = build_recommendations([], drivers, _concentration())
        assert recs == []

    def test_zero_exposure_negative_driver_is_skipped(self):
        from runtime.impact.recommendations import build_recommendations

        drivers = [_driver("liquidity", "negative", exposed_weight_pct=0.0)]
        recs = build_recommendations([], drivers, _concentration())
        assert recs == []

    def test_high_concentration_adds_diversification_recommendation(self):
        from runtime.impact.recommendations import build_recommendations

        holdings = [
            {"symbol": "AAPL", "market_value": 800.0},
            {"symbol": "MSFT", "market_value": 200.0},
        ]
        recs = build_recommendations(holdings, [], _concentration(hhi=6800.0))
        assert len(recs) == 1
        assert "diversifica" in recs[0].action.lower() or "concentra" in recs[0].action.lower()
        assert recs[0].affected_holdings == ["AAPL", "MSFT"]

    def test_low_concentration_does_not_add_recommendation(self):
        from runtime.impact.recommendations import build_recommendations

        recs = build_recommendations([], [], _concentration(hhi=1000.0))
        assert recs == []

    def test_empty_portfolio_no_holdings_no_crash(self):
        from runtime.impact.recommendations import build_recommendations

        recs = build_recommendations([], [], _concentration(hhi=0.0, holding_count=0))
        assert recs == []


class TestBuildOpportunities:
    def test_positive_driver_produces_opportunity(self):
        from runtime.impact.recommendations import build_opportunities

        drivers = [_driver("commodities", "positive", symbols=["GLD"])]
        opps = build_opportunities(drivers)
        assert len(opps) == 1
        assert opps[0].affected_holdings == ["GLD"]

    def test_negative_driver_does_not_produce_opportunity(self):
        from runtime.impact.recommendations import build_opportunities

        drivers = [_driver("commodities", "negative")]
        assert build_opportunities(drivers) == []
