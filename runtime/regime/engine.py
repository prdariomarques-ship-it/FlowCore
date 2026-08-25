"""RegimeEngine — deterministic per-dimension regime classification.

The Regime Engine stage of the SCPX pipeline, directly after Macro Score
Engine. Classifies each dimension's z-score into a discrete label using a
fixed, documented threshold — no LLM, no fusion of dimensions into a
single "master regime" (that would be an interpretive leap the current
3-dimension coverage doesn't support; see
docs/SPEC_SPRINT19_MACRO_SCORE_ENGINE.md's "insufficient_data over
fabrication" precedent, applied the same way here).

Composes MacroScoreEngine rather than depending on it internally —
unknown-dimension errors (MacroScoreError) simply propagate, no
duplicated validation.
"""

from __future__ import annotations

from runtime.macro_score.engine import MacroScoreEngine
from runtime.macro_score.score import DimensionScore
from runtime.regime.signal import RegimeSignal

DEFAULT_THRESHOLD = 1.0


class RegimeEngine:
    def __init__(self, macro_score_engine: MacroScoreEngine, threshold: float = DEFAULT_THRESHOLD) -> None:
        self._macro_score_engine = macro_score_engine
        self._threshold = threshold

    async def classify(self, dimension: str) -> RegimeSignal:
        score = await self._macro_score_engine.compute_score(dimension)
        return self._classify_score(score)

    async def classify_all(self) -> list[RegimeSignal]:
        scores = await self._macro_score_engine.compute_all()
        return [self._classify_score(s) for s in scores]

    def _classify_score(self, score: DimensionScore) -> RegimeSignal:
        if score.status == "insufficient_data" or score.score is None:
            regime = "insufficient_data"
        elif score.score > self._threshold:
            regime = "elevated"
        elif score.score < -self._threshold:
            regime = "depressed"
        else:
            regime = "neutral"
        return RegimeSignal(
            dimension=score.dimension,
            regime=regime,
            score=score.score,
            threshold=self._threshold,
            computed_at=score.computed_at,
        )
