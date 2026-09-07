"""PersistentMetricsSink -- the "table-backed implementation" that
runtime/llm/metrics.py's own docstring names as a future pure addition.

Wraps an InMemoryMetrics instance for snapshot()/GET /api/llm/status'
existing process-lifetime shape (unchanged), and additionally writes
every call to storage/llm_call_repo.py so cost/call history survives a
restart -- the data agents/observer_loop.py's autonomous reasoning calls
and the interactive chat both need for the Agent Runtime's cost
dashboard (§18-19).
"""

from __future__ import annotations

from runtime.llm.metrics import InMemoryMetrics, MetricsSink

__all__ = ["PersistentMetricsSink"]


class PersistentMetricsSink(MetricsSink):
    def __init__(self, repo: "object | None" = None) -> None:
        from storage.llm_call_repo import LLMCallRepository

        self._memory = InMemoryMetrics()
        self._repo = repo or LLMCallRepository()

    def record_call(
        self, provider: str, model: str, latency_ms: float, success: bool, error: str | None,
        purpose: str | None = None, tokens: int | None = None, office_id: str | None = None,
    ) -> None:
        self._memory.record_call(provider, model, latency_ms, success, error, purpose=purpose)
        try:
            self._repo.record_call(
                provider, model, latency_ms, success, error,
                purpose=purpose, tokens=tokens, office_id=office_id,
            )
        except Exception:
            pass  # persisted history is observability, not load-bearing -- never break a real LLM call over it

    def snapshot(self) -> list[dict]:
        return self._memory.snapshot()
