"""Tests for runtime.llm.policy.LocalFirstPolicy and agent_ask cloud env var.

Default semantics (no allow_cloud key): local providers only — cloud is
never a silent fallback. Cloud requires an explicit opt-in via
metadata["allow_cloud"]=True or the FLOWCORE_AGENT_ALLOW_CLOUD env var.
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


class TestAgentAskCloudEnvVar:
    """FLOWCORE_AGENT_ALLOW_CLOUD env var gates cloud fallback in agent_ask()."""

    def _get_meta(self, monkeypatch, value=None):
        """Call _agent_ask_metadata() with a fresh env state."""
        import os
        if value is None:
            monkeypatch.delenv("FLOWCORE_AGENT_ALLOW_CLOUD", raising=False)
        else:
            monkeypatch.setenv("FLOWCORE_AGENT_ALLOW_CLOUD", value)
        # _agent_ask_metadata reads os.getenv() at call time — no reload needed.
        import service as svc
        return svc._agent_ask_metadata()

    def test_local_only_when_env_absent(self, monkeypatch):
        """Without FLOWCORE_AGENT_ALLOW_CLOUD, no allow_cloud key in metadata."""
        meta = self._get_meta(monkeypatch)
        assert not meta.get("allow_cloud")

    def test_cloud_enabled_when_env_true(self, monkeypatch):
        meta = self._get_meta(monkeypatch, "true")
        assert meta.get("allow_cloud") is True

    def test_cloud_enabled_when_env_1(self, monkeypatch):
        meta = self._get_meta(monkeypatch, "1")
        assert meta.get("allow_cloud") is True

    def test_cloud_enabled_when_env_yes(self, monkeypatch):
        meta = self._get_meta(monkeypatch, "yes")
        assert meta.get("allow_cloud") is True

    def test_local_only_when_env_false(self, monkeypatch):
        meta = self._get_meta(monkeypatch, "false")
        assert not meta.get("allow_cloud")

    def test_local_only_when_env_empty(self, monkeypatch):
        meta = self._get_meta(monkeypatch, "")
        assert not meta.get("allow_cloud")

    def test_purpose_key_always_present(self, monkeypatch):
        """purpose key must always be in metadata regardless of cloud setting."""
        for val in (None, "true", "false"):
            meta = self._get_meta(monkeypatch, val)
            assert meta.get("purpose") == "chat"
