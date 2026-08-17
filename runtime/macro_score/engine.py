"""MacroScoreEngine — deterministic, explainable per-dimension scoring.

For each source in a dimension: pull its event history over a trailing
window from EventRepository, compute a z-score for the latest value
against that window's own mean/stdev (population stdev — window sizes are
small, and pstdev avoids the n=1 edge case sample stdev has). A source
with fewer than min_samples events in the window contributes no z-score
(but its sample count is still reported) — a dimension with no source
meeting that bar gets status="insufficient_data" and score=None, never a
fabricated number. The dimension score is the mean of its available
per-source z-scores (a v1 placeholder — per-source weighting is a later,
non-breaking refinement, see docs/SPEC_SPRINT19_MACRO_SCORE_ENGINE.md).
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime, timedelta

from runtime.macro_score.dimension import DIMENSIONS
from runtime.macro_score.score import DimensionScore


class MacroScoreError(RuntimeError):
    """Raised for an unknown dimension."""


class MacroScoreEngine:
    def __init__(self, event_repo, window_days: int = 30, min_samples: int = 5) -> None:
        self._event_repo = event_repo
        self._window_days = window_days
        self._min_samples = min_samples

    async def compute_score(self, dimension: str) -> DimensionScore:
        if dimension not in DIMENSIONS:
            raise MacroScoreError(f"Unknown dimension: {dimension!r}")

        since = (datetime.now(UTC) - timedelta(days=self._window_days)).isoformat()
        z_scores: dict[str, float] = {}
        sample_counts: dict[str, int] = {}

        for source in DIMENSIONS[dimension]:
            events = await self._event_repo.list_events(source=source, since=since)
            sample_counts[source] = len(events)
            if len(events) < self._min_samples:
                continue
            values = [e["payload"]["value"] for e in events if "value" in e.get("payload", {})]
            if len(values) < self._min_samples:
                continue
            latest = values[0]  # list_events orders newest-first
            mean = statistics.mean(values)
            stdev = statistics.pstdev(values)
            z_scores[source] = (latest - mean) / stdev if stdev else 0.0

        if not z_scores:
            return DimensionScore(
                dimension=dimension,
                status="insufficient_data",
                score=None,
                window_days=self._window_days,
                z_scores={},
                sample_counts=sample_counts,
                computed_at=datetime.now(UTC).isoformat(),
            )

        score = statistics.mean(z_scores.values())
        return DimensionScore(
            dimension=dimension,
            status="scored",
            score=score,
            window_days=self._window_days,
            z_scores=z_scores,
            sample_counts=sample_counts,
            computed_at=datetime.now(UTC).isoformat(),
        )

    async def compute_all(self) -> list[DimensionScore]:
        scores = [await self.compute_score(dimension) for dimension in DIMENSIONS]
        # Read-only additive hook: snapshot every computation into
        # Macro Score History (D-1/D-5/D-20/D-60 views). A failure here
        # must never break the live scores.
        try:
            from runtime.market_intelligence.score_history import record_scores

            record_scores([s.to_dict() for s in scores])
        except Exception:  # noqa: BLE001
            pass
        return scores
