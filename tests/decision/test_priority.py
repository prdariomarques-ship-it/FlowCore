"""Tests for runtime.decision.priority (Sprint 24).

Core tier — pure arithmetic, no network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _driver(direction="negative", regime_score=2.5, exposed_weight_pct=50.0, confidence_score=0.8):
    from runtime.impact.models import DriverImpact

    return DriverImpact(
        dimension="risk_sentiment",
        driver="d",
        regime="elevated",
        regime_score=regime_score,
        direction=direction,
        expected_impact="strong",
        confidence_score=confidence_score,
        confidence_label="high",
        exposed_weight_pct=exposed_weight_pct,
        positive_weight_pct=exposed_weight_pct if direction == "positive" else 0.0,
        negative_weight_pct=exposed_weight_pct if direction == "negative" else 0.0,
        reason="r",
    )


class TestMacroSeverity:
    def test_none_score_is_zero(self):
        from runtime.decision.priority import macro_severity

        assert macro_severity(None, 1.0) == 0.0

    def test_at_threshold_is_partial(self):
        from runtime.decision.priority import macro_severity

        assert macro_severity(1.0, 1.0) == pytest.approx(1 / 3)

    def test_caps_at_one(self):
        from runtime.decision.priority import macro_severity

        assert macro_severity(10.0, 1.0) == 1.0

    def test_negative_score_uses_magnitude(self):
        from runtime.decision.priority import macro_severity

        assert macro_severity(-3.0, 1.0) == 1.0


class TestImpactContribution:
    def test_negative_direction_uses_negative_weight(self):
        from runtime.decision.priority import impact_contribution

        d = _driver(direction="negative", exposed_weight_pct=50.0, confidence_score=0.8)
        assert impact_contribution(d) == pytest.approx(min(1.0, 50.0 * 0.8 / 100.0))

    def test_positive_direction_uses_positive_weight(self):
        from runtime.decision.priority import impact_contribution

        d = _driver(direction="positive", exposed_weight_pct=50.0, confidence_score=0.8)
        assert impact_contribution(d) == pytest.approx(min(1.0, 50.0 * 0.8 / 100.0))

    def test_neutral_direction_is_zero(self):
        from runtime.decision.priority import impact_contribution

        d = _driver(direction="neutral")
        assert impact_contribution(d) == 0.0

    def test_caps_at_one(self):
        from runtime.decision.priority import impact_contribution

        d = _driver(direction="negative", exposed_weight_pct=100.0, confidence_score=0.95)
        assert impact_contribution(d) <= 1.0


class TestPriorityScore:
    def test_higher_exposure_gives_higher_score(self):
        from runtime.decision.priority import priority_score

        low = priority_score(_driver(exposed_weight_pct=10.0), confidence=0.5, urgency="LOW")
        high = priority_score(_driver(exposed_weight_pct=90.0), confidence=0.5, urgency="LOW")
        assert high > low

    def test_higher_urgency_gives_higher_score(self):
        from runtime.decision.priority import priority_score

        low = priority_score(_driver(), confidence=0.5, urgency="LOW")
        high = priority_score(_driver(), confidence=0.5, urgency="CRITICAL")
        assert high > low

    def test_score_is_bounded_0_1(self):
        from runtime.decision.priority import priority_score

        s = priority_score(_driver(exposed_weight_pct=100.0, confidence_score=0.95), confidence=1.0, urgency="CRITICAL")
        assert 0.0 <= s <= 1.0


class TestConcentrationPriorityScore:
    def test_higher_hhi_gives_higher_score(self):
        from runtime.decision.priority import concentration_priority_score

        class FakeConcentration:
            def __init__(self, hhi, top):
                self.hhi = hhi
                self.top_holding_weight_pct = top

        low = concentration_priority_score(FakeConcentration(1500, 20.0), confidence=0.5, urgency="LOW")
        high = concentration_priority_score(FakeConcentration(9000, 90.0), confidence=0.5, urgency="HIGH")
        assert high > low


class TestMagnitudeLabel:
    def test_zero_is_none(self):
        from runtime.decision.priority import magnitude_label

        assert magnitude_label(0.0) == "NONE"

    def test_thresholds(self):
        from runtime.decision.priority import magnitude_label

        assert magnitude_label(0.05) == "LOW"
        assert magnitude_label(0.20) == "MODERATE"
        assert magnitude_label(0.50) == "HIGH"
