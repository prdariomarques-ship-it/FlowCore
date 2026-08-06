"""Tests for runtime.narrative.engine.NarrativeEngine (Sprint 25,
migrated to the LLM Router).

Core tier — the Router is a real LLMRouter wired with a fake in-test
LLMProvider (no network, no runtime/ollama.py involved), exercising the
actual Router/provider/policy machinery end-to-end rather than mocking
at the engine boundary. Async calls driven via asyncio.run(), matching
this repo's established convention.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _decision(priority=1, action="Reduzir duracao", urgency="HIGH", confidence=0.9, expected_impact="HIGH"):
    return {
        "priority": priority,
        "action": action,
        "urgency": urgency,
        "confidence": confidence,
        "expected_impact": expected_impact,
        "reason_chain": ["passo 1", "passo 2"],
        "recommended_products": [],
    }


def _report(decisions=None, overall_priority="HIGH", overall_confidence=0.8):
    return {
        "overall_priority": overall_priority,
        "overall_confidence": overall_confidence,
        "decisions": decisions or [],
        "top_risks": [],
        "top_opportunities": [],
        "portfolio_score": {"overall": None},
    }


class _FakeProvider:
    """A minimal in-test LLMProvider — real class implementing the real
    interface, not a mock, so these tests exercise the actual Router
    dispatch path."""

    name = "fake"

    def __init__(self, available=True, text="Uma narrativa gerada.", fail_with=None):
        self._available = available
        self._text = text
        self._fail_with = fail_with

    def is_available(self):
        return self._available

    def generate(self, request):
        from runtime.llm import LLMResponse

        if self._fail_with:
            raise self._fail_with
        return LLMResponse(text=self._text, provider=self.name, model="fake-model", latency_ms=1.0)


def _router_with(provider):
    from runtime.llm import LocalFirstPolicy, ProviderRegistry
    from runtime.llm.router import LLMRouter

    registry = ProviderRegistry()
    registry.register(provider)

    class _AlwaysAllowPolicy(LocalFirstPolicy):
        """Test-only policy: every registered provider is eligible,
        regardless of name — LocalFirstPolicy's real "ollama"-only
        default would exclude our fake provider entirely."""

        def choose(self, request, available):
            return list(available)

    return LLMRouter(registry, _AlwaysAllowPolicy())


class TestGenerateSuccess:
    def test_llm_success_returns_llm_source(self):
        from runtime.narrative.engine import NarrativeEngine

        router = _router_with(_FakeProvider(text="  Uma narrativa gerada.  "))
        engine = NarrativeEngine(router)
        result = asyncio.run(engine.generate(1, _report(decisions=[_decision()])))

        assert result.source == "llm"
        assert result.model == "fake-model"
        assert result.narrative == "Uma narrativa gerada."
        assert result.fallback_reason is None

    def test_prompt_is_built_from_the_decision_report(self):
        from runtime.narrative.engine import NarrativeEngine

        captured = {}

        class _CapturingProvider(_FakeProvider):
            def generate(self, request):
                captured["prompt"] = request.prompt
                return super().generate(request)

        router = _router_with(_CapturingProvider())
        engine = NarrativeEngine(router)
        asyncio.run(engine.generate(1, _report(decisions=[_decision(action="Aumentar caixa em USD")])))

        assert "Aumentar caixa em USD" in captured["prompt"]

    def test_request_never_allows_cloud(self):
        """The narrative request's metadata must never set allow_cloud
        -- this is the structural guarantee that a narrative call can
        never reach a cloud provider without a deliberate code change."""
        from runtime.narrative.engine import NarrativeEngine

        captured = {}

        class _CapturingProvider(_FakeProvider):
            def generate(self, request):
                captured["metadata"] = request.metadata
                return super().generate(request)

        router = _router_with(_CapturingProvider())
        engine = NarrativeEngine(router)
        asyncio.run(engine.generate(1, _report()))

        assert captured["metadata"].get("allow_cloud") is not True


class TestGenerateFallback:
    def test_provider_failure_falls_back(self):
        from runtime.llm import LLMProviderUnavailableError
        from runtime.narrative.engine import NarrativeEngine

        router = _router_with(_FakeProvider(fail_with=LLMProviderUnavailableError("down")))
        engine = NarrativeEngine(router)
        result = asyncio.run(engine.generate(1, _report(decisions=[_decision()])))

        assert result.source == "fallback"
        assert result.model is None
        assert "down" in result.fallback_reason

    def test_no_available_provider_falls_back(self):
        from runtime.narrative.engine import NarrativeEngine

        router = _router_with(_FakeProvider(available=False))
        engine = NarrativeEngine(router)
        result = asyncio.run(engine.generate(1, _report(decisions=[_decision()])))

        assert result.source == "fallback"
        assert result.narrative  # non-empty

    def test_fallback_narrative_reflects_the_decision_report(self):
        from runtime.llm import LLMProviderUnavailableError
        from runtime.narrative.engine import NarrativeEngine

        router = _router_with(_FakeProvider(fail_with=LLMProviderUnavailableError("down")))
        engine = NarrativeEngine(router)
        result = asyncio.run(
            engine.generate(
                1, _report(decisions=[_decision(action="Aumentar liquidez em USD")], overall_priority="CRITICAL")
            )
        )

        assert "CRITICAL" in result.narrative
        assert "Aumentar liquidez em USD" in result.narrative
        assert "passo 1" in result.narrative

    def test_fallback_with_no_decisions_is_still_non_empty(self):
        from runtime.llm import LLMProviderUnavailableError
        from runtime.narrative.engine import NarrativeEngine

        router = _router_with(_FakeProvider(fail_with=LLMProviderUnavailableError("down")))
        engine = NarrativeEngine(router)
        result = asyncio.run(engine.generate(1, _report(decisions=[])))

        assert result.narrative
        assert result.source == "fallback"

    def test_only_llm_errors_are_caught_others_propagate(self):
        """A genuine bug (e.g. a KeyError from a malformed decision_report)
        must not be silently swallowed as a "fallback" -- only the
        documented LLMError family triggers the graceful path."""
        from runtime.narrative.engine import NarrativeEngine

        router = _router_with(_FakeProvider(fail_with=RuntimeError("not an LLMError")))
        engine = NarrativeEngine(router)
        try:
            asyncio.run(engine.generate(1, _report()))
            raised = False
        except RuntimeError:
            raised = True
        assert raised
