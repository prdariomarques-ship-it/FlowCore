"""Tests for runtime.regime.engine.RegimeEngine.

Core tier — no yfinance/optional-dependency guard needed. Uses a real
MacroScoreEngine backed by a tmp_path SQLite EventRepository, same
pattern as tests/macro_score/test_engine.py.
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


def _seed(repo, source, values):
    now = datetime.now(UTC)
    n = len(values)
    for i, v in enumerate(values):
        asyncio.run(
            repo.insert_event(
                {
                    "id": str(uuid.uuid4()),
                    "timestamp": (now - timedelta(days=n - i)).isoformat(),
                    "source": source,
                    "category": "test",
                    "symbol": source.upper(),
                    "event": "x",
                    "severity": "info",
                    "confidence": 0.95,
                    "payload": {"value": v},
                    "metadata": {},
                }
            )
        )


def _engines(tmp_path):
    from storage import EventRepository

    from runtime.macro_score import MacroScoreEngine
    from runtime.regime import RegimeEngine

    repo = EventRepository(db_path=str(tmp_path / "events.db"))
    mse = MacroScoreEngine(repo, min_samples=5)
    return repo, RegimeEngine(mse)


class TestClassify:
    def test_no_data_is_insufficient(self, tmp_path):
        _repo, regime = _engines(tmp_path)
        signal = asyncio.run(regime.classify("risk_sentiment"))
        assert signal.regime == "insufficient_data"
        assert signal.score is None

    def test_spike_is_elevated(self, tmp_path):
        repo, regime = _engines(tmp_path)
        _seed(repo, "vix", [10, 11, 12, 13, 14, 20])
        signal = asyncio.run(regime.classify("risk_sentiment"))
        assert signal.regime == "elevated"
        assert signal.score > 1.0

    def test_drop_is_depressed(self, tmp_path):
        repo, regime = _engines(tmp_path)
        _seed(repo, "vix", [20, 19, 18, 17, 16, 10])
        signal = asyncio.run(regime.classify("risk_sentiment"))
        assert signal.regime == "depressed"
        assert signal.score < -1.0

    def test_stable_is_neutral(self, tmp_path):
        repo, regime = _engines(tmp_path)
        _seed(repo, "vix", [15, 15, 15, 15, 15])
        signal = asyncio.run(regime.classify("risk_sentiment"))
        assert signal.regime == "neutral"
        assert signal.score == 0.0

    def test_unknown_dimension_raises(self, tmp_path):
        from runtime.macro_score import MacroScoreError

        _repo, regime = _engines(tmp_path)
        with pytest.raises(MacroScoreError):
            asyncio.run(regime.classify("bogus"))

    def test_threshold_boundary_is_not_elevated(self, tmp_path):
        """A z-score of exactly the threshold should NOT count as elevated
        (strictly greater-than), matching the documented >threshold rule."""
        from runtime.regime import RegimeEngine

        repo, _regime = _engines(tmp_path)
        _seed(repo, "vix", [10, 10, 10, 10, 10])
        from runtime.macro_score import MacroScoreEngine

        mse = MacroScoreEngine(repo, min_samples=5)
        regime_zero_threshold = RegimeEngine(mse, threshold=0.0)
        signal = asyncio.run(regime_zero_threshold.classify("risk_sentiment"))
        # all-equal values -> z=0.0, and threshold=0.0 -> 0.0 is not > 0.0 nor < -0.0
        assert signal.regime == "neutral"


class TestClassifyAll:
    def test_returns_every_dimension(self, tmp_path):
        from runtime.macro_score import DIMENSIONS

        _repo, regime = _engines(tmp_path)
        signals = asyncio.run(regime.classify_all())
        assert {s.dimension for s in signals} == set(DIMENSIONS)
