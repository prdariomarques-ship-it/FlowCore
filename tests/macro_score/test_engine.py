"""Tests for runtime.macro_score.engine.MacroScoreEngine.

Core tier — no yfinance/optional-dependency guard needed. Uses a real
EventRepository backed by a tmp_path SQLite file, not a real Observer
fetch — this engine never touches the network.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _seed(repo, source, values, category="test", days_ago_start=None):
    now = datetime.now(UTC)
    n = len(values)
    for i, v in enumerate(values):
        days_ago = (n - i) if days_ago_start is None else days_ago_start - i
        asyncio.run(
            repo.insert_event(
                {
                    "id": str(uuid.uuid4()),
                    "timestamp": (now - timedelta(days=days_ago)).isoformat(),
                    "source": source,
                    "category": category,
                    "symbol": source.upper(),
                    "event": "x",
                    "severity": "info",
                    "confidence": 0.95,
                    "payload": {"value": v},
                    "metadata": {},
                }
            )
        )


def _repo(tmp_path):
    from storage import EventRepository

    return EventRepository(db_path=str(tmp_path / "events.db"))


class TestComputeScore:
    def test_unknown_dimension_raises(self, tmp_path):
        from runtime.macro_score import MacroScoreError, MacroScoreEngine

        engine = MacroScoreEngine(_repo(tmp_path))
        with pytest.raises(MacroScoreError, match="Unknown dimension"):
            asyncio.run(engine.compute_score("bogus"))

    def test_no_data_is_insufficient(self, tmp_path):
        from runtime.macro_score import MacroScoreEngine

        engine = MacroScoreEngine(_repo(tmp_path))
        score = asyncio.run(engine.compute_score("risk_sentiment"))
        assert score.status == "insufficient_data"
        assert score.score is None
        assert score.sample_counts == {"vix": 0}
        assert score.z_scores == {}

    def test_sufficient_data_computes_deterministic_zscore(self, tmp_path):
        from runtime.macro_score import MacroScoreEngine

        repo = _repo(tmp_path)
        # values ordered oldest->newest; latest (last) is 20, an outlier
        _seed(repo, "vix", [10, 11, 12, 13, 14, 20])
        engine = MacroScoreEngine(repo, min_samples=5)

        score = asyncio.run(engine.compute_score("risk_sentiment"))
        assert score.status == "scored"
        mean = sum([10, 11, 12, 13, 14, 20]) / 6
        variance = sum((x - mean) ** 2 for x in [10, 11, 12, 13, 14, 20]) / 6
        stdev = variance**0.5
        expected_z = (20 - mean) / stdev
        assert score.z_scores["vix"] == pytest.approx(expected_z)
        assert score.score == pytest.approx(expected_z)
        assert score.sample_counts == {"vix": 6}

    def test_multi_source_dimension_partial_coverage(self, tmp_path):
        """One source (oil) has enough samples, the other (gold) doesn't —
        gold is absent from z_scores but its real count still shows up."""
        from runtime.macro_score import MacroScoreEngine

        repo = _repo(tmp_path)
        _seed(repo, "oil", [70, 71, 72, 73, 79])
        _seed(repo, "gold", [4000, 4010])  # below min_samples
        engine = MacroScoreEngine(repo, min_samples=5)

        score = asyncio.run(engine.compute_score("commodities"))
        assert score.status == "scored"
        assert set(score.z_scores.keys()) == {"oil"}
        assert score.sample_counts == {"oil": 5, "gold": 2}

    def test_all_sources_below_min_samples_is_insufficient(self, tmp_path):
        from runtime.macro_score import MacroScoreEngine

        repo = _repo(tmp_path)
        _seed(repo, "oil", [70, 71])
        _seed(repo, "gold", [4000])
        engine = MacroScoreEngine(repo, min_samples=5)

        score = asyncio.run(engine.compute_score("commodities"))
        assert score.status == "insufficient_data"
        assert score.score is None
        assert score.sample_counts == {"oil": 2, "gold": 1}

    def test_zero_stdev_yields_zero_zscore_not_a_crash(self, tmp_path):
        from runtime.macro_score import MacroScoreEngine

        repo = _repo(tmp_path)
        _seed(repo, "vix", [15, 15, 15, 15, 15])
        engine = MacroScoreEngine(repo, min_samples=5)

        score = asyncio.run(engine.compute_score("risk_sentiment"))
        assert score.status == "scored"
        assert score.z_scores["vix"] == 0.0
        assert score.score == 0.0

    def test_respects_window_days(self, tmp_path):
        """An old sample outside the window shouldn't count toward
        min_samples or the mean/stdev computation."""
        from runtime.macro_score import MacroScoreEngine

        repo = _repo(tmp_path)
        _seed(repo, "vix", [10, 11, 12, 13, 14], days_ago_start=5)  # within window
        _seed(repo, "vix", [999], days_ago_start=400)  # way outside a 30-day window
        engine = MacroScoreEngine(repo, window_days=30, min_samples=5)

        score = asyncio.run(engine.compute_score("risk_sentiment"))
        assert score.sample_counts["vix"] == 5
        assert 999 not in score.z_scores.values()


class TestComputeAll:
    def test_returns_every_dimension(self, tmp_path):
        from runtime.macro_score import DIMENSIONS, MacroScoreEngine

        engine = MacroScoreEngine(_repo(tmp_path))
        scores = asyncio.run(engine.compute_all())
        assert {s.dimension for s in scores} == set(DIMENSIONS)
