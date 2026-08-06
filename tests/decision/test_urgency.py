"""Tests for runtime.decision.urgency (Sprint 24)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestClassifyUrgency:
    def test_insufficient_data_regime_is_always_low(self):
        from runtime.decision.urgency import classify_urgency

        assert classify_urgency("strong", 0.95, "insufficient_data") == "LOW"

    def test_strong_impact_high_confidence_is_critical(self):
        from runtime.decision.urgency import classify_urgency

        assert classify_urgency("strong", 0.9, "elevated") == "CRITICAL"

    def test_strong_impact_medium_confidence_is_high(self):
        from runtime.decision.urgency import classify_urgency

        assert classify_urgency("strong", 0.6, "elevated") == "HIGH"

    def test_moderate_impact_low_confidence_is_medium(self):
        from runtime.decision.urgency import classify_urgency

        assert classify_urgency("moderate", 0.35, "elevated") == "MEDIUM"

    def test_mild_impact_very_low_confidence_is_low(self):
        from runtime.decision.urgency import classify_urgency

        assert classify_urgency("mild", 0.1, "elevated") == "LOW"

    def test_none_impact_is_low(self):
        from runtime.decision.urgency import classify_urgency

        assert classify_urgency("none", 0.9, "elevated") == "LOW"


class TestUrgencyWeight:
    def test_ordering(self):
        from runtime.decision.urgency import urgency_weight

        assert urgency_weight("CRITICAL") > urgency_weight("HIGH") > urgency_weight("MEDIUM") > urgency_weight("LOW")

    def test_unknown_urgency_defaults_to_low_weight(self):
        from runtime.decision.urgency import urgency_weight

        assert urgency_weight("bogus") == urgency_weight("LOW")
