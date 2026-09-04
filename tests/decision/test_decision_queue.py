"""Tests for runtime.decision.decision_queue (Sprint 24)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _decision(priority_score, urgency="MEDIUM", confidence=0.5):
    from runtime.decision.models import Decision

    return Decision(
        id=f"d-{priority_score}",
        kind="risk",
        dimension="risk_sentiment",
        priority=0,
        priority_score=priority_score,
        urgency=urgency,
        confidence=confidence,
        expected_impact="MODERATE",
        estimated_risk_reduction="MODERATE",
        action="a",
        reason="r",
    )


class TestBuildQueue:
    def test_sorts_descending_by_priority_score(self):
        from runtime.decision.decision_queue import build_queue

        decisions = [_decision(0.2), _decision(0.9), _decision(0.5)]
        ordered = build_queue(decisions)
        assert [d.priority_score for d in ordered] == [0.9, 0.5, 0.2]

    def test_assigns_1_based_rank(self):
        from runtime.decision.decision_queue import build_queue

        decisions = [_decision(0.2), _decision(0.9), _decision(0.5)]
        ordered = build_queue(decisions)
        assert [d.priority for d in ordered] == [1, 2, 3]

    def test_empty_list(self):
        from runtime.decision.decision_queue import build_queue

        assert build_queue([]) == []


class TestOverallPriority:
    def test_top_decisions_urgency_wins(self):
        from runtime.decision.decision_queue import build_queue, overall_priority

        decisions = build_queue([_decision(0.2, urgency="LOW"), _decision(0.9, urgency="CRITICAL")])
        assert overall_priority(decisions) == "CRITICAL"

    def test_empty_is_none(self):
        from runtime.decision.decision_queue import overall_priority

        assert overall_priority([]) == "NONE"


class TestOverallConfidence:
    def test_empty_is_zero(self):
        from runtime.decision.decision_queue import overall_confidence

        assert overall_confidence([]) == 0.0

    def test_weighted_toward_higher_priority_decisions(self):
        from runtime.decision.decision_queue import overall_confidence

        decisions = [_decision(0.9, confidence=0.9), _decision(0.1, confidence=0.1)]
        result = overall_confidence(decisions)
        # weighted average should sit closer to 0.9 (the higher-scored decision) than a plain mean (0.5)
        assert result > 0.5

    def test_zero_total_weight_falls_back_to_plain_mean(self):
        from runtime.decision.decision_queue import overall_confidence

        decisions = [_decision(0.0, confidence=0.4), _decision(0.0, confidence=0.6)]
        assert overall_confidence(decisions) == pytest.approx(0.5)
