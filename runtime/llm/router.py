"""LLMRouter -- the single entrypoint every caller in FlowCore uses to
reach an LLM. Composes ProviderRegistry (what's available) + a
RoutingPolicy (what's allowed) + retry (per-provider transient-failure
handling) + fallback (try the next allowed provider) + MetricsSink +
CacheBackend + BudgetPolicy.

This is what "the rest of FlowCore must never know whether the request
is executed by Claude, DeepSeek, OpenAI, Gemini, Ollama or another
provider" means concretely: every caller constructs one LLMRequest and
gets one LLMResponse back. Which concrete provider actually ran is
recorded on the response (`response.provider`) for observability, never
selected by the caller directly.
"""

from __future__ import annotations

from dataclasses import replace

from runtime.llm.budget import BudgetPolicy, NoLimitBudget
from runtime.llm.cache import CacheBackend, NullCache, cache_key_for
from runtime.llm.metrics import MetricsSink, NullMetrics
from runtime.llm.models import LLMAllProvidersFailedError, LLMError, LLMRequest, LLMResponse
from runtime.llm.policy import RoutingPolicy
from runtime.llm.registry import ProviderRegistry
from runtime.llm.retry import with_retry

__all__ = ["LLMRouter"]


class LLMRouter:
    def __init__(
        self,
        registry: ProviderRegistry,
        policy: RoutingPolicy,
        metrics: MetricsSink | None = None,
        cache: CacheBackend | None = None,
        budget: BudgetPolicy | None = None,
        retry_attempts: int = 2,
        retry_backoff_seconds: float = 1.0,
    ) -> None:
        self._registry = registry
        self._policy = policy
        self._metrics = metrics or NullMetrics()
        self._cache = cache or NullCache()
        self._budget = budget or NoLimitBudget()
        self._retry_backoff_seconds = retry_backoff_seconds
        self._retry_attempts = retry_attempts

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Sync, blocking (matches every provider's own generate()
        shape) -- async callers wrap this in asyncio.to_thread(), the
        same convention service.ask() already used for runtime/ollama.py
        directly before the Router existed."""
        key = cache_key_for(request)
        cached = self._cache.get(key)
        if cached is not None:
            return replace(cached, cached=True)

        available = self._registry.available_names()
        # Defensive: a misbehaving custom RoutingPolicy could return a name
        # outside `available` (e.g. a typo, or a provider that was
        # available a moment ago and isn't now). Filtering here means a
        # policy bug degrades to "that provider is skipped," never an
        # uncaught ProviderNotFoundError escaping generate() as something
        # other than a clean LLMError.
        order = [name for name in self._policy.choose(request, available) if name in available]

        errors: list[str] = []
        for name in order:
            provider = self._registry.get(name)
            try:
                self._budget.check(name)
                response = with_retry(
                    lambda p=provider: p.generate(request),
                    attempts=self._retry_attempts,
                    backoff_seconds=self._retry_backoff_seconds,
                )
            except LLMError as e:
                errors.append(f"{name}: {e}")
                self._metrics.record_call(name, request.model or "?", 0.0, False, str(e))
                continue
            self._budget.record(name, response)
            self._metrics.record_call(name, response.model, response.latency_ms, True, None)
            self._cache.set(key, response)
            return response

        detail = "; ".join(errors) if errors else "no provider available for this request"
        raise LLMAllProvidersFailedError(detail)

    def status(self) -> dict:
        """Introspection surface for GET /api/llm/status -- registered
        providers, which are currently available, and metrics."""
        return {
            "providers": self._registry.names(),
            "available": self._registry.available_names(),
            "metrics": self._metrics.snapshot(),
        }
