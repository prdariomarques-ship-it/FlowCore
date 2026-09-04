"""Tests for runtime.llm.policy.LocalFirstPolicy -- the Policy Engine's
default: local-first, cloud only ever opt-in, never a silent fallback.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestLocalFirstPolicy:
    def test_ollama_only_by_default(self):
        from runtime.llm import LLMRequest, LocalFirstPolicy

        policy = LocalFirstPolicy()
        order = policy.choose(LLMRequest(prompt="x"), ["ollama", "openrouter"])
        assert order == ["ollama"]

    def test_cloud_excluded_even_if_no_local_available(self):
        """No silent fallback to cloud -- if local isn't available and
        the caller didn't opt in, the result is empty, not cloud."""
        from runtime.llm import LLMRequest, LocalFirstPolicy

        policy = LocalFirstPolicy()
        order = policy.choose(LLMRequest(prompt="x"), ["openrouter"])
        assert order == []

    def test_cloud_included_when_explicitly_allowed(self):
        from runtime.llm import LLMRequest, LocalFirstPolicy

        policy = LocalFirstPolicy()
        order = policy.choose(LLMRequest(prompt="x", metadata={"allow_cloud": True}), ["ollama", "openrouter"])
        assert order == ["ollama", "openrouter"]

    def test_allow_cloud_false_behaves_like_default(self):
        from runtime.llm import LLMRequest, LocalFirstPolicy

        policy = LocalFirstPolicy()
        order = policy.choose(LLMRequest(prompt="x", metadata={"allow_cloud": False}), ["ollama", "openrouter"])
        assert order == ["ollama"]

    def test_unregistered_provider_names_are_ignored(self):
        from runtime.llm import LLMRequest, LocalFirstPolicy

        policy = LocalFirstPolicy()
        order = policy.choose(
            LLMRequest(prompt="x", metadata={"allow_cloud": True}), ["ollama", "some_future_provider"]
        )
        assert order == ["ollama", "some_future_provider"]

    def test_custom_provider_order_is_respected_when_cloud_is_allowed(self):
        from runtime.llm import LLMRequest, LocalFirstPolicy

        policy = LocalFirstPolicy(("openrouter", "ollama", "deepseek"))
        order = policy.choose(
            LLMRequest(prompt="x", metadata={"allow_cloud": True}), ["ollama", "openrouter", "deepseek"]
        )
        assert order == ["openrouter", "ollama", "deepseek"]

    def test_custom_cloud_priority_still_cannot_bypass_local_first_boundary(self):
        from runtime.llm import LLMRequest, LocalFirstPolicy

        policy = LocalFirstPolicy(("openrouter", "deepseek"))
        assert policy.choose(LLMRequest(prompt="x"), ["openrouter", "deepseek"]) == []
