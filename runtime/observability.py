"""FlowCore Observability — lightweight in-process metrics.

Tracks request counts, latency and errors per endpoint.
No external dependency — pure stdlib. Expose via /api/metrics.

Usage (in route handlers):
    from runtime.observability import record
    t0 = time.perf_counter()
    ...
    record("market_fx", latency_ms=(time.perf_counter()-t0)*1000, error=False)
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

_start_time = time.time()


@dataclass
class EndpointStats:
    name: str
    calls: int = 0
    errors: int = 0
    total_latency_ms: float = 0.0
    min_latency_ms: float = float("inf")
    max_latency_ms: float = 0.0
    last_called: float = 0.0
    last_error: str = ""

    def record(self, latency_ms: float, error: bool = False, error_msg: str = "") -> None:
        self.calls += 1
        self.total_latency_ms += latency_ms
        self.min_latency_ms = min(self.min_latency_ms, latency_ms)
        self.max_latency_ms = max(self.max_latency_ms, latency_ms)
        self.last_called = time.time()
        if error:
            self.errors += 1
            self.last_error = error_msg[:200]

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.calls if self.calls else 0.0

    @property
    def error_rate(self) -> float:
        return self.errors / self.calls if self.calls else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "calls": self.calls,
            "errors": self.errors,
            "error_rate": round(self.error_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "min_latency_ms": round(self.min_latency_ms, 1) if self.calls else None,
            "max_latency_ms": round(self.max_latency_ms, 1),
            "last_called": self.last_called,
            "last_error": self.last_error,
        }


class MetricsStore:
    def __init__(self) -> None:
        self._endpoints: dict[str, EndpointStats] = defaultdict(lambda: EndpointStats(""))
        self._ai_calls: list[dict[str, Any]] = []  # rolling last 100
        self._ai_tokens_total: int = 0
        self._ai_cost_usd_total: float = 0.0

    def record(self, endpoint: str, latency_ms: float, error: bool = False, error_msg: str = "") -> None:
        if endpoint not in self._endpoints:
            self._endpoints[endpoint] = EndpointStats(endpoint)
        self._endpoints[endpoint].record(latency_ms, error=error, error_msg=error_msg)

    def record_ai(self, model_id: str, task: str, latency_ms: float, tokens: int = 0, success: bool = True) -> None:
        self._ai_calls.append({
            "model_id": model_id,
            "task": task,
            "latency_ms": round(latency_ms, 1),
            "tokens": tokens,
            "success": success,
            "ts": time.time(),
        })
        self._ai_calls = self._ai_calls[-100:]
        self._ai_tokens_total += tokens

    def summary(self) -> dict[str, Any]:
        uptime = time.time() - _start_time
        endpoints = [s.to_dict() for s in sorted(self._endpoints.values(), key=lambda s: -s.calls)]
        recent_ai = self._ai_calls[-10:]
        ai_success = sum(1 for c in self._ai_calls if c["success"])
        return {
            "uptime_seconds": round(uptime, 1),
            "endpoints": endpoints,
            "ai": {
                "total_calls": len(self._ai_calls),
                "success_rate": round(ai_success / max(1, len(self._ai_calls)), 3),
                "total_tokens": self._ai_tokens_total,
                "recent": recent_ai,
            },
        }

    def reset(self) -> None:
        self._endpoints.clear()
        self._ai_calls.clear()
        self._ai_tokens_total = 0


_store = MetricsStore()


def record(endpoint: str, latency_ms: float, error: bool = False, error_msg: str = "") -> None:
    _store.record(endpoint, latency_ms, error=error, error_msg=error_msg)


def record_ai(model_id: str, task: str, latency_ms: float, tokens: int = 0, success: bool = True) -> None:
    _store.record_ai(model_id, task, latency_ms, tokens=tokens, success=success)


def get_metrics() -> dict[str, Any]:
    return _store.summary()


def reset_metrics() -> None:
    _store.reset()
