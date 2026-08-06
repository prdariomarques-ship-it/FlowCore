"""Tests for runtime.llm.router.LLMRouter -- the orchestration of
registry + policy + retry + fallback + metrics + cache + budget.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _StubProvider:
    def __init__(self, name, available=True, text="ok", fail_with=None, fail_times=0):
        self.name = name
        self._available = available
        self._text = text
        self._fail_with = fail_with
        self._fail_times = fail_times
        self.call_count = 0

    def is_available(self):
        return self._available

    def generate(self, request):
        from runtime.llm import LLMResponse

        self.call_count += 1
        if self._fail_with and self.call_count <= self._fail_times:
            raise self._fail_with
        if self._fail_with and self._fail_times == -1:  # always fail
            raise self._fail_with
        return LLMResponse(text=self._text, provider=self.name, model="stub-model", latency_ms=5.0)


class _AllowAllPolicy:
    def choose(self, request, available):
        return list(available)


def _build(providers, policy=None, **router_kwargs):
    from runtime.llm import ProviderRegistry
    from runtime.llm.router import LLMRouter

    registry = ProviderRegistry()
    for p in providers:
        registry.register(p)
    return LLMRouter(registry, policy or _AllowAllPolicy(), **router_kwargs)


class TestGenerateSuccess:
    def test_returns_response_from_first_allowed_provider(self):
        from runtime.llm import LLMRequest

        p = _StubProvider("ollama", text="hello")
        router = _build([p])
        resp = router.generate(LLMRequest(prompt="x"))
        assert resp.text == "hello"
        assert resp.provider == "ollama"
        assert resp.cached is False


class TestFallbackBetweenProviders:
    def test_falls_through_to_next_provider_on_failure(self):
        from runtime.llm import LLMProviderUnavailableError, LLMRequest

        failing = _StubProvider("a", fail_with=LLMProviderUnavailableError("down"), fail_times=-1)
        working = _StubProvider("b", text="from b")
        router = _build([failing, working], retry_attempts=1)
        resp = router.generate(LLMRequest(prompt="x"))
        assert resp.provider == "b"
        assert resp.text == "from b"

    def test_all_providers_failing_raises(self):
        from runtime.llm import LLMAllProvidersFailedError, LLMProviderUnavailableError, LLMRequest

        a = _StubProvider("a", fail_with=LLMProviderUnavailableError("down a"), fail_times=-1)
        b = _StubProvider("b", fail_with=LLMProviderUnavailableError("down b"), fail_times=-1)
        router = _build([a, b], retry_attempts=1)
        with pytest.raises(LLMAllProvidersFailedError, match="down a.*down b"):
            router.generate(LLMRequest(prompt="x"))

    def test_no_provider_available_raises(self):
        from runtime.llm import LLMAllProvidersFailedError, LLMRequest

        p = _StubProvider("a", available=False)
        router = _build([p])
        with pytest.raises(LLMAllProvidersFailedError):
            router.generate(LLMRequest(prompt="x"))

    def test_empty_policy_result_raises(self):
        from runtime.llm import LLMAllProvidersFailedError, LLMRequest

        class _DenyAllPolicy:
            def choose(self, request, available):
                return []

        p = _StubProvider("a")
        router = _build([p], policy=_DenyAllPolicy())
        with pytest.raises(LLMAllProvidersFailedError):
            router.generate(LLMRequest(prompt="x"))

    def test_buggy_policy_naming_an_unavailable_provider_is_skipped_not_crashed(self):
        """A misbehaving custom RoutingPolicy returning a name outside
        `available` must degrade to "that entry is skipped," never an
        uncaught ProviderNotFoundError escaping generate()."""
        from runtime.llm import LLMAllProvidersFailedError, LLMRequest

        class _BuggyPolicy:
            def choose(self, request, available):
                return ["typo-name", *available]

        p = _StubProvider("a", available=False)  # not actually available
        router = _build([p], policy=_BuggyPolicy())
        with pytest.raises(LLMAllProvidersFailedError):
            router.generate(LLMRequest(prompt="x"))


class TestRetryWithinRouter:
    def test_transient_failure_recovers_via_retry_before_falling_over(self):
        from runtime.llm import LLMProviderUnavailableError, LLMRequest

        # fails once, then succeeds -- should recover via retry, not fallback
        flaky = _StubProvider("a", fail_with=LLMProviderUnavailableError("blip"), fail_times=1, text="recovered")
        other = _StubProvider("b", text="should not be used")
        router = _build([flaky, other], retry_attempts=2, retry_backoff_seconds=0)
        resp = router.generate(LLMRequest(prompt="x"))
        assert resp.provider == "a"
        assert resp.text == "recovered"


class TestMetricsIntegration:
    def test_records_success_and_failure(self):
        from runtime.llm import InMemoryMetrics, LLMRequest

        p = _StubProvider("a", text="ok")
        metrics = InMemoryMetrics()
        router = _build([p], metrics=metrics)
        router.generate(LLMRequest(prompt="x"))
        snap = metrics.snapshot()
        assert snap[0]["provider"] == "a"
        assert snap[0]["successes"] == 1


class TestCacheIntegration:
    def test_second_identical_call_is_served_from_cache(self):
        from runtime.llm import LLMRequest
        from runtime.llm.cache import InMemoryTTLCache

        p = _StubProvider("a", text="first")
        cache = InMemoryTTLCache(ttl_seconds=60)
        router = _build([p], cache=cache)

        req = LLMRequest(prompt="same prompt")
        r1 = router.generate(req)
        assert r1.cached is False
        assert p.call_count == 1

        r2 = router.generate(req)
        assert r2.cached is True
        assert r2.text == "first"
        assert p.call_count == 1  # provider not called again


class TestBudgetIntegration:
    def test_budget_exceeded_falls_through_to_next_provider(self):
        from runtime.llm import LLMAllProvidersFailedError, LLMRequest
        from runtime.llm.budget import CallCountBudget

        a = _StubProvider("a", text="from a")
        budget = CallCountBudget(max_calls={"a": 0})  # a is immediately over budget
        router = _build([a], budget=budget)
        with pytest.raises(LLMAllProvidersFailedError, match="exceeded"):
            router.generate(LLMRequest(prompt="x"))


class TestStatus:
    def test_status_reports_providers_and_availability(self):
        from runtime.llm import InMemoryMetrics, LLMRequest

        available = _StubProvider("a", available=True)
        unavailable = _StubProvider("b", available=False)
        router = _build([available, unavailable], metrics=InMemoryMetrics())
        router.generate(LLMRequest(prompt="x"))

        status = router.status()
        assert set(status["providers"]) == {"a", "b"}
        assert status["available"] == ["a"]
        assert len(status["metrics"]) >= 1
