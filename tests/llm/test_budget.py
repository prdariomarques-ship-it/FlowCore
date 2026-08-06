"""Tests for runtime.llm.budget."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _response():
    from runtime.llm import LLMResponse

    return LLMResponse(text="x", provider="ollama", model="m", latency_ms=1.0)


class TestNoLimitBudget:
    def test_never_raises(self):
        from runtime.llm import NoLimitBudget

        b = NoLimitBudget()
        for _ in range(100):
            b.check("ollama")
            b.record("ollama", _response())


class TestCallCountBudget:
    def test_allows_calls_under_limit(self):
        from runtime.llm.budget import CallCountBudget

        b = CallCountBudget(max_calls={"openrouter": 3})
        for _ in range(3):
            b.check("openrouter")
            b.record("openrouter", _response())

    def test_raises_once_limit_reached(self):
        from runtime.llm import LLMBudgetExceededError
        from runtime.llm.budget import CallCountBudget

        b = CallCountBudget(max_calls={"openrouter": 2})
        b.check("openrouter")
        b.record("openrouter", _response())
        b.check("openrouter")
        b.record("openrouter", _response())
        with pytest.raises(LLMBudgetExceededError):
            b.check("openrouter")

    def test_provider_without_configured_limit_is_unlimited(self):
        from runtime.llm.budget import CallCountBudget

        b = CallCountBudget(max_calls={"openrouter": 1})
        for _ in range(10):
            b.check("ollama")
            b.record("ollama", _response())

    def test_window_prunes_old_calls(self):
        from runtime.llm.budget import CallCountBudget

        b = CallCountBudget(max_calls={"openrouter": 1}, window_seconds=0.05)
        b.check("openrouter")
        b.record("openrouter", _response())
        import time

        time.sleep(0.1)
        b.check("openrouter")  # should not raise -- the old call fell out of the window
