"""Tests for runtime.impact.scenarios.evaluate() — the deterministic
holding-vs-driver-rule classification (Sprint 23).

Core tier — pure computation over plain dicts, no network.
"""

from __future__ import annotations

import sys
from pathlib import Path

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


class TestInsufficientData:
    def test_insufficient_data_short_circuits(self):
        from runtime.impact.scenarios import evaluate

        holdings = [_holding("AAPL", 1000.0, sector="Technology")]
        impact = evaluate(holdings, _signal("risk_sentiment", "insufficient_data", score=None))
        assert impact.regime == "insufficient_data"
        assert impact.direction == "insufficient_data"
        assert impact.confidence_score == 0.0
        assert impact.buckets == []


class TestUnknownDimension:
    def test_unknown_dimension_raises(self):
        from runtime.impact.scenarios import evaluate, ImpactError

        with pytest.raises(ImpactError, match="Unknown impact dimension"):
            evaluate([], _signal("not_a_real_dimension", "elevated"))


class TestHardColumnClassification:
    def test_sector_negative_when_elevated(self):
        from runtime.impact.scenarios import evaluate

        holdings = [_holding("AAPL", 1000.0, sector="Technology")]
        impact = evaluate(holdings, _signal("risk_sentiment", "elevated"))
        assert impact.direction == "negative"
        assert impact.negative_weight_pct == 100.0
        assert impact.affected_symbols == ["AAPL"]

    def test_sector_positive_when_elevated(self):
        from runtime.impact.scenarios import evaluate

        holdings = [_holding("XLU", 1000.0, sector="Utilities")]
        impact = evaluate(holdings, _signal("risk_sentiment", "elevated"))
        assert impact.direction == "positive"
        assert impact.positive_weight_pct == 100.0

    def test_direction_flips_when_depressed(self):
        from runtime.impact.scenarios import evaluate

        holdings = [_holding("AAPL", 1000.0, sector="Technology")]
        impact = evaluate(holdings, _signal("risk_sentiment", "depressed"))
        assert impact.direction == "positive"
        assert impact.positive_weight_pct == 100.0

    def test_neutral_regime_never_assigns_direction(self):
        from runtime.impact.scenarios import evaluate

        holdings = [_holding("AAPL", 1000.0, sector="Technology")]
        impact = evaluate(holdings, _signal("risk_sentiment", "neutral", score=0.3))
        assert impact.direction == "neutral"

    def test_asset_class_future_matches_commodities_positive(self):
        from runtime.impact.scenarios import evaluate

        holdings = [_holding("GC=F", 1000.0, asset_class="future")]
        impact = evaluate(holdings, _signal("commodities", "elevated"))
        assert impact.direction == "positive"

    def test_never_classifies_by_ticker_symbol_alone(self):
        """Architectural boundary: a well-known cash-proxy/gold/commodity
        ticker with no sector/asset_class/country/soft-attribute signal
        is simply unclassified — the Impact Engine has no symbol
        allowlist to fall back on (that's runtime/product_mapping/'s
        job, downstream of a generic recommendation)."""
        from runtime.impact.scenarios import evaluate

        holdings = [_holding("SGOV", 1000.0)]  # no sector/asset_class/country set
        impact = evaluate(holdings, _signal("liquidity", "elevated"))
        assert impact.direction == "neutral"
        assert impact.exposed_weight_pct == 0.0

    def test_em_proxy_matches_non_us_country_for_risk_sentiment(self):
        from runtime.impact.scenarios import evaluate

        holdings = [_holding("PBR", 1000.0, country="Brazil")]
        impact = evaluate(holdings, _signal("risk_sentiment", "elevated"))
        assert impact.direction == "negative"

    def test_us_country_does_not_trigger_em_proxy(self):
        from runtime.impact.scenarios import evaluate

        holdings = [_holding("KO", 1000.0, country="United States")]
        impact = evaluate(holdings, _signal("risk_sentiment", "elevated"))
        assert impact.direction == "neutral"

    def test_unclassified_holding_is_simply_unmatched(self):
        from runtime.impact.scenarios import evaluate

        holdings = [_holding("XYZ", 1000.0)]
        impact = evaluate(holdings, _signal("liquidity", "elevated"))
        assert impact.direction == "neutral"
        assert impact.exposed_weight_pct == 0.0


class TestSoftAttributeOverride:
    def test_recognized_high_overrides_hard_baseline(self):
        from runtime.impact.scenarios import evaluate

        # sector "Financial Services" is hard-positive for liquidity, but
        # a recognized "high" interest_rate_sensitivity tag overrides it
        # to negative for this specific holding.
        holdings = [
            _holding(
                "XYZ",
                1000.0,
                sector="Financial Services",
                attributes={"interest_rate_sensitivity": "alta"},
            )
        ]
        impact = evaluate(holdings, _signal("liquidity", "elevated"))
        assert impact.direction == "negative"
        assert impact.buckets[0].source == "soft"

    def test_unrecognized_value_falls_through_to_hard_baseline(self):
        from runtime.impact.scenarios import evaluate

        holdings = [
            _holding(
                "AAPL",
                1000.0,
                sector="Technology",
                attributes={"risk_attributes": "depende do dia"},
            )
        ]
        impact = evaluate(holdings, _signal("risk_sentiment", "elevated"))
        assert impact.direction == "negative"
        assert impact.buckets[0].source == "hard"

    def test_medium_falls_through_to_hard_baseline(self):
        from runtime.impact.scenarios import evaluate

        holdings = [
            _holding(
                "AAPL",
                1000.0,
                sector="Technology",
                attributes={"risk_attributes": "média"},
            )
        ]
        impact = evaluate(holdings, _signal("risk_sentiment", "elevated"))
        assert impact.buckets[0].source == "hard"


class TestEdgeCases:
    def test_empty_holdings(self):
        from runtime.impact.scenarios import evaluate

        impact = evaluate([], _signal("risk_sentiment", "elevated"))
        assert impact.exposed_weight_pct == 0.0
        assert impact.buckets == []

    def test_missing_prices_excluded_but_not_crashing(self):
        from runtime.impact.scenarios import evaluate

        holdings = [_holding("AAPL", None, sector="Technology")]
        impact = evaluate(holdings, _signal("risk_sentiment", "elevated"))
        assert impact.exposed_weight_pct == 0.0
        assert impact.buckets == []

    def test_expected_impact_thresholds(self):
        from runtime.impact.scenarios import evaluate

        holdings = [
            _holding("AAPL", 5000.0, sector="Technology"),
            _holding("KO", 5000.0, country="United States"),
        ]
        impact = evaluate(holdings, _signal("risk_sentiment", "elevated"))
        assert impact.exposed_weight_pct == 50.0
        assert impact.expected_impact == "strong"

    def test_confidence_scales_with_score_magnitude(self):
        from runtime.impact.scenarios import evaluate

        holdings = [_holding("AAPL", 1000.0, sector="Technology")]
        low = evaluate(holdings, _signal("risk_sentiment", "elevated", score=1.1))
        high = evaluate(holdings, _signal("risk_sentiment", "elevated", score=4.0))
        assert low.confidence_score < high.confidence_score
        assert high.confidence_score <= 0.95
