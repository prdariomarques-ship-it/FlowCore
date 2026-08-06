"""Tests for runtime.impact.engine.ImpactEngine (Sprint 23).

Core tier — RegimeEngine is mocked (its own coverage lives in
tests/regime/), so these tests exercise ImpactEngine's own aggregation
(_aggregate_overall/_risk_score) and orchestration logic in isolation.
Async calls are driven via asyncio.run(), matching tests/regime/
test_classifier.py's convention (no pytest-asyncio mark in this repo).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _holding(symbol, market_value, **asset_fields):
    asset = None
    if market_value is not None:
        asset = {
            "asset_class": asset_fields.get("asset_class"),
            "sector": asset_fields.get("sector"),
            "country": asset_fields.get("country"),
            "attributes": asset_fields.get("attributes", {}),
        }
    return {"symbol": symbol, "market_value": market_value, "asset": asset}


def _signal(dimension, regime, score=2.5, threshold=1.0):
    from runtime.regime.signal import RegimeSignal

    return RegimeSignal(dimension=dimension, regime=regime, score=score, threshold=threshold, computed_at="t")


def _fake_regime_engine(signals):
    engine = AsyncMock()
    engine.classify_all.return_value = signals
    return engine


class TestComputeBasics:
    def test_all_insufficient_data_gives_insufficient_overall(self):
        from runtime.impact.engine import ImpactEngine

        signals = [
            _signal("liquidity", "insufficient_data", score=None),
            _signal("commodities", "insufficient_data", score=None),
            _signal("risk_sentiment", "insufficient_data", score=None),
        ]
        engine = ImpactEngine(_fake_regime_engine(signals))
        holdings = [_holding("AAPL", 1000.0, sector="Technology")]
        report = asyncio.run(engine.compute(1, holdings))

        assert report.overall_impact == "insufficient_data"
        assert report.confidence == 0.0
        assert len(report.drivers) == 3
        assert report.affected_dimensions == []

    def test_negative_driver_yields_negative_overall(self):
        from runtime.impact.engine import ImpactEngine

        signals = [
            _signal("liquidity", "insufficient_data", score=None),
            _signal("commodities", "insufficient_data", score=None),
            _signal("risk_sentiment", "elevated", score=3.0),
        ]
        engine = ImpactEngine(_fake_regime_engine(signals))
        holdings = [_holding("AAPL", 1000.0, sector="Technology")]
        report = asyncio.run(engine.compute(1, holdings))

        assert report.overall_impact == "negative"
        assert report.confidence > 0.0
        assert "risk_sentiment" in report.affected_dimensions
        assert len(report.recommendations) >= 1

    def test_positive_driver_yields_positive_overall(self):
        from runtime.impact.engine import ImpactEngine

        signals = [
            _signal("liquidity", "insufficient_data", score=None),
            _signal("commodities", "insufficient_data", score=None),
            _signal("risk_sentiment", "elevated", score=3.0),
        ]
        engine = ImpactEngine(_fake_regime_engine(signals))
        holdings = [_holding("XLU", 1000.0, sector="Utilities")]
        report = asyncio.run(engine.compute(1, holdings))

        assert report.overall_impact == "positive"
        assert len(report.opportunities) >= 1

    def test_neutral_regime_nets_to_neutral_not_a_fabricated_direction(self):
        """A neutral regime still has real data (unlike
        insufficient_data), so it correctly nets to "neutral" overall
        when it's the only contributing driver — not "insufficient_data",
        which is reserved for "no real data at all"."""
        from runtime.impact.engine import ImpactEngine

        signals = [
            _signal("liquidity", "neutral", score=0.2),
            _signal("commodities", "insufficient_data", score=None),
            _signal("risk_sentiment", "insufficient_data", score=None),
        ]
        engine = ImpactEngine(_fake_regime_engine(signals))
        holdings = [_holding("AAPL", 1000.0, sector="Technology")]
        report = asyncio.run(engine.compute(1, holdings))

        assert report.overall_impact == "neutral"
        liquidity_driver = next(d for d in report.drivers if d.dimension == "liquidity")
        assert liquidity_driver.direction == "neutral"


class TestEdgeCases:
    def test_empty_portfolio(self):
        from runtime.impact.engine import ImpactEngine

        signals = [_signal("risk_sentiment", "elevated", score=3.0)]
        engine = ImpactEngine(_fake_regime_engine(signals))
        report = asyncio.run(engine.compute(1, []))

        assert report.overall_impact == "insufficient_data"
        assert report.recommendations == []
        assert report.opportunities == []
        assert report.unvalued_count == 0

    def test_all_missing_prices(self):
        from runtime.impact.engine import ImpactEngine

        signals = [_signal("risk_sentiment", "elevated", score=3.0)]
        engine = ImpactEngine(_fake_regime_engine(signals))
        holdings = [_holding("AAPL", None, sector="Technology")]
        report = asyncio.run(engine.compute(1, holdings))

        assert report.unvalued_count == 1
        assert report.overall_impact == "insufficient_data"

    def test_unknown_regime_dimension_is_skipped_not_crashed(self):
        """A dimension RegimeEngine reports that isn't in RULES (e.g. if
        DIMENSIONS ever grows ahead of the rule table) is silently
        excluded from drivers rather than raising."""
        from runtime.impact.engine import ImpactEngine

        signals = [_signal("some_future_dimension", "elevated", score=3.0)]
        engine = ImpactEngine(_fake_regime_engine(signals))
        report = asyncio.run(engine.compute(1, [_holding("AAPL", 1000.0, sector="Technology")]))

        assert report.drivers == []
        assert report.overall_impact == "insufficient_data"

    def test_high_concentration_contributes_to_risk_score(self):
        from runtime.impact.engine import ImpactEngine

        signals = [
            _signal("liquidity", "insufficient_data", score=None),
            _signal("commodities", "insufficient_data", score=None),
            _signal("risk_sentiment", "insufficient_data", score=None),
        ]
        engine = ImpactEngine(_fake_regime_engine(signals))
        holdings = [_holding("AAPL", 1000.0, sector="Technology")]  # single holding -> HHI 10000
        report = asyncio.run(engine.compute(1, holdings))

        assert report.portfolio_risk_score == pytest.approx(40.0)  # 0.4 * (10000/100)
