"""BudgetPolicy -- guards a provider from being over-called. Matters
most for paid cloud providers (OpenRouter bills per token); irrelevant
for local Ollama, which NoLimitBudget (the default for every provider
unless explicitly configured otherwise) correctly reflects.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from runtime.llm.models import LLMBudgetExceededError, LLMResponse

__all__ = ["BudgetPolicy", "NoLimitBudget", "CallCountBudget"]


class BudgetPolicy(ABC):
    @abstractmethod
    def check(self, provider: str) -> None:
        """Raises LLMBudgetExceededError if `provider` may not be
        called right now."""

    @abstractmethod
    def record(self, provider: str, response: LLMResponse) -> None: ...


class NoLimitBudget(BudgetPolicy):
    def check(self, provider: str) -> None:
        pass

    def record(self, provider: str, response: LLMResponse) -> None:
        pass


class CallCountBudget(BudgetPolicy):
    """Simple in-memory per-provider call-count limit within a rolling
    window. A starting point -- persisted/cost-based budgets (real
    OpenRouter $ spend, tracked via the response's tokens_estimated) can
    replace this later without changing BudgetPolicy's interface."""

    def __init__(self, max_calls: dict[str, int], window_seconds: float = 3600.0) -> None:
        self._max_calls = max_calls
        self._window = window_seconds
        self._calls: dict[str, list[float]] = {}

    def check(self, provider: str) -> None:
        limit = self._max_calls.get(provider)
        if limit is None:
            return
        self._prune(provider)
        if len(self._calls.get(provider, [])) >= limit:
            raise LLMBudgetExceededError(f"Provider {provider!r} exceeded {limit} calls / {self._window:.0f}s")

    def record(self, provider: str, response: LLMResponse) -> None:
        self._calls.setdefault(provider, []).append(time.monotonic())

    def _prune(self, provider: str) -> None:
        cutoff = time.monotonic() - self._window
        calls = self._calls.get(provider, [])
        self._calls[provider] = [t for t in calls if t >= cutoff]
