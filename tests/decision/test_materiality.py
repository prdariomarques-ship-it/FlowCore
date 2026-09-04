"""Tests for runtime.decision.materiality (Sprint 24)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _driver(regime="elevated", direction="negative", exposed_weight_pct=50.0):
    from runtime.impact.models import DriverImpact

    return DriverImpact(
        dimension="risk_sentiment",
        driver="d",
        regime=regime,
        regime_score=2.0,
        direction=direction,
        expected_impact="strong",
        confidence_score=0.9,
        confidence_label="high",
        exposed_weight_pct=exposed_weight_pct,
        positive_weight_pct=0.0,
        negative_weight_pct=exposed_weight_pct,
        reason="r",
    )


class TestIsMaterial:
    def test_insufficient_data_is_never_material(self):
        from runtime.decision.materiality import is_material

        assert is_material(_driver(regime="insufficient_data")) is False

    def test_neutral_direction_is_never_material(self):
        from runtime.decision.materiality import is_material

        assert is_material(_driver(direction="neutral")) is False

    def test_below_threshold_is_not_material(self):
        from runtime.decision.materiality import is_material

        assert is_material(_driver(exposed_weight_pct=2.0)) is False

    def test_at_or_above_threshold_is_material(self):
        from runtime.decision.materiality import is_material, MIN_EXPOSED_WEIGHT_PCT

        assert is_material(_driver(exposed_weight_pct=MIN_EXPOSED_WEIGHT_PCT)) is True
        assert is_material(_driver(exposed_weight_pct=50.0)) is True
