"""Tests for runtime.decision.confidence (Sprint 24)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestDecisionConfidence:
    def test_full_exposure_keeps_full_confidence(self):
        from runtime.decision.confidence import decision_confidence

        assert decision_confidence(0.9, 50.0) == pytest.approx(0.9)

    def test_low_exposure_scales_down_confidence(self):
        from runtime.decision.confidence import decision_confidence

        assert decision_confidence(0.9, 5.0) == pytest.approx(0.09, abs=0.01)

    def test_zero_exposure_is_zero_confidence(self):
        from runtime.decision.confidence import decision_confidence

        assert decision_confidence(0.9, 0.0) == 0.0

    def test_exposure_above_full_threshold_does_not_exceed_driver_confidence(self):
        from runtime.decision.confidence import decision_confidence

        assert decision_confidence(0.8, 100.0) == pytest.approx(0.8)

    def test_custom_full_confidence_threshold(self):
        from runtime.decision.confidence import decision_confidence

        assert decision_confidence(1.0, 25.0, full_confidence_at_pct=25.0) == pytest.approx(1.0)
