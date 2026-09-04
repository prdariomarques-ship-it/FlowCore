"""Tests for runtime.llm.metrics."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestNullMetrics:
    def test_records_nothing_and_snapshot_is_empty(self):
        from runtime.llm import NullMetrics

        m = NullMetrics()
        m.record_call("ollama", "model", 10.0, True, None)
        assert m.snapshot() == []


class TestInMemoryMetrics:
    def test_snapshot_empty_initially(self):
        from runtime.llm import InMemoryMetrics

        assert InMemoryMetrics().snapshot() == []

    def test_records_success(self):
        from runtime.llm import InMemoryMetrics

        m = InMemoryMetrics()
        m.record_call("ollama", "qwen3:4b", 120.0, True, None)
        snap = m.snapshot()
        assert len(snap) == 1
        assert snap[0]["provider"] == "ollama"
        assert snap[0]["calls"] == 1
        assert snap[0]["successes"] == 1
        assert snap[0]["failures"] == 0
        assert snap[0]["avg_latency_ms"] == 120.0
        assert snap[0]["last_error"] is None

    def test_records_failure(self):
        from runtime.llm import InMemoryMetrics

        m = InMemoryMetrics()
        m.record_call("ollama", "?", 0.0, False, "boom")
        snap = m.snapshot()
        assert snap[0]["failures"] == 1
        assert snap[0]["last_error"] == "boom"
        assert snap[0]["avg_latency_ms"] is None  # no successes yet

    def test_averages_latency_across_multiple_successes(self):
        from runtime.llm import InMemoryMetrics

        m = InMemoryMetrics()
        m.record_call("ollama", "m", 100.0, True, None)
        m.record_call("ollama", "m", 200.0, True, None)
        snap = m.snapshot()
        assert snap[0]["avg_latency_ms"] == 150.0

    def test_tracks_multiple_providers_independently(self):
        from runtime.llm import InMemoryMetrics

        m = InMemoryMetrics()
        m.record_call("ollama", "m", 10.0, True, None)
        m.record_call("openrouter", "m", 20.0, True, None)
        providers = {row["provider"] for row in m.snapshot()}
        assert providers == {"ollama", "openrouter"}
