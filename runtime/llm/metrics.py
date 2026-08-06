"""MetricsSink -- realizes ROADMAP.md's existing "Telemetry" sketch
(per-provider call count, latency, errors) as a proper interface instead
of a someday-item. InMemoryMetrics is a real, useful default (process-
lifetime counters, enough for `flowcore.py llm status` / a debugging
session); swapping in a persisted table-backed implementation later is
a pure addition -- this interface doesn't change.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

__all__ = ["MetricsSink", "NullMetrics", "InMemoryMetrics", "ProviderMetrics"]


@dataclass
class ProviderMetrics:
    provider: str
    calls: int = 0
    successes: int = 0
    failures: int = 0
    total_latency_ms: float = 0.0
    last_error: str | None = None
    last_call_at: float | None = None

    def to_dict(self) -> dict:
        avg_latency = (self.total_latency_ms / self.successes) if self.successes else None
        return {
            "provider": self.provider,
            "calls": self.calls,
            "successes": self.successes,
            "failures": self.failures,
            "avg_latency_ms": avg_latency,
            "last_error": self.last_error,
            "last_call_at": self.last_call_at,
        }


class MetricsSink(ABC):
    @abstractmethod
    def record_call(self, provider: str, model: str, latency_ms: float, success: bool, error: str | None) -> None: ...

    @abstractmethod
    def snapshot(self) -> list[dict]:
        """Returns a list of ProviderMetrics.to_dict() — the exact shape
        exposed by GET /api/llm/status."""


class NullMetrics(MetricsSink):
    def record_call(self, provider: str, model: str, latency_ms: float, success: bool, error: str | None) -> None:
        pass

    def snapshot(self) -> list[dict]:
        return []


class InMemoryMetrics(MetricsSink):
    def __init__(self) -> None:
        self._by_provider: dict[str, ProviderMetrics] = {}

    def record_call(self, provider: str, model: str, latency_ms: float, success: bool, error: str | None) -> None:
        m = self._by_provider.setdefault(provider, ProviderMetrics(provider=provider))
        m.calls += 1
        m.last_call_at = time.time()
        if success:
            m.successes += 1
            m.total_latency_ms += latency_ms
        else:
            m.failures += 1
            m.last_error = error

    def snapshot(self) -> list[dict]:
        return [m.to_dict() for m in self._by_provider.values()]
