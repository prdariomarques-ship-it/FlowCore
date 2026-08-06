"""Tests for runtime.decision.reason_chain (Sprint 24)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _driver(direction="negative", regime="elevated", buckets=None):
    from runtime.impact.models import DriverImpact

    return DriverImpact(
        dimension="risk_sentiment",
        driver="Risk Off",
        regime=regime,
        regime_score=2.5,
        direction=direction,
        expected_impact="strong",
        confidence_score=0.9,
        confidence_label="high",
        exposed_weight_pct=40.0,
        positive_weight_pct=0.0,
        negative_weight_pct=40.0,
        reason="Aversao a risco elevada penaliza ativos de risco.",
        buckets=buckets or [],
    )


def _recommendation():
    from runtime.impact.models import Recommendation

    return Recommendation(
        action_key="increase_usd_liquidity",
        action="Aumentar liquidez em USD",
        reason="r",
        confidence=0.9,
        dimension="risk_sentiment",
    )


def _bucket(label="Technology", weight_pct=40.0):
    from runtime.impact.models import ImpactBucket

    return ImpactBucket(
        label=label,
        matched_direction="negative",
        source="hard",
        market_value=100.0,
        weight_pct=weight_pct,
        holding_count=1,
        symbols=["AAPL"],
    )


class TestBuildForDriver:
    def test_returns_eight_steps(self):
        from runtime.decision.reason_chain import build_for_driver

        chain = build_for_driver(_driver(buckets=[_bucket()]), _recommendation())
        assert len(chain) == 8

    def test_includes_regime_score(self):
        from runtime.decision.reason_chain import build_for_driver

        chain = build_for_driver(_driver(buckets=[_bucket()]), _recommendation())
        assert "2.50" in chain[0] or "+2.50" in chain[0]

    def test_includes_recommendation_action(self):
        from runtime.decision.reason_chain import build_for_driver

        chain = build_for_driver(_driver(buckets=[_bucket()]), _recommendation())
        assert any("Aumentar liquidez em USD" in step for step in chain)

    def test_negative_direction_mentions_no_mitigation(self):
        from runtime.decision.reason_chain import build_for_driver

        chain = build_for_driver(_driver(direction="negative", buckets=[_bucket()]), _recommendation())
        consequence = next(s for s in chain if s.startswith("Se nada for feito"))
        assert "mitig" in consequence.lower()

    def test_positive_direction_mentions_missed_opportunity(self):
        from runtime.decision.reason_chain import build_for_driver

        chain = build_for_driver(_driver(direction="positive", buckets=[_bucket()]), _recommendation())
        consequence = next(s for s in chain if s.startswith("Se nada for feito"))
        assert "oportunidade" in consequence.lower()

    def test_no_buckets_does_not_crash(self):
        from runtime.decision.reason_chain import build_for_driver

        chain = build_for_driver(_driver(buckets=[]), _recommendation())
        assert len(chain) == 8

    def test_unknown_dimension_falls_back_to_raw_name(self):
        from runtime.decision.reason_chain import build_for_driver
        from runtime.impact.models import DriverImpact

        d = DriverImpact(
            dimension="some_new_dimension",
            driver="d",
            regime="elevated",
            regime_score=1.5,
            direction="negative",
            expected_impact="mild",
            confidence_score=0.6,
            confidence_label="medium",
            exposed_weight_pct=10.0,
            positive_weight_pct=0.0,
            negative_weight_pct=10.0,
            reason="r",
        )
        chain = build_for_driver(d, _recommendation())
        assert "some_new_dimension" in chain[0]


class TestBuildForConcentration:
    def test_returns_eight_steps(self):
        from runtime.decision.reason_chain import build_for_concentration
        from runtime.exposure import ConcentrationReport

        c = ConcentrationReport(
            total_market_value=1000.0,
            top_holding_weight_pct=60.0,
            top_5_weight_pct=100.0,
            hhi=4200.0,
            holding_count=3,
            unvalued_count=0,
            computed_at="t",
        )
        chain = build_for_concentration(c, _recommendation())
        assert len(chain) == 8
        assert "60.0" in chain[0]
        assert "4200" in chain[0]
