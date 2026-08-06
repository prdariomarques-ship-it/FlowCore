"""Tests for runtime.llm.providers.ollama_provider.OllamaProvider."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestIsAvailable:
    def test_true_when_endpoint_discoverable(self):
        from runtime.llm.providers.ollama_provider import OllamaProvider

        with patch("runtime.llm.providers.ollama_provider.discover_ollama_endpoint", return_value="http://x"):
            assert OllamaProvider().is_available() is True

    def test_false_on_discovery_error(self):
        from runtime.llm.providers.ollama_provider import OllamaProvider
        from runtime.ollama import OllamaDiscoveryError

        with patch(
            "runtime.llm.providers.ollama_provider.discover_ollama_endpoint", side_effect=OllamaDiscoveryError("no")
        ):
            assert OllamaProvider().is_available() is False


class TestGenerate:
    def test_success_returns_llm_response(self):
        from runtime.llm import LLMRequest
        from runtime.llm.providers.ollama_provider import OllamaProvider

        with (
            patch(
                "runtime.llm.providers.ollama_provider.discover_ollama_endpoint", return_value="http://127.0.0.1:11434"
            ),
            patch("runtime.llm.providers.ollama_provider.discover_default_model", return_value="qwen3:4b"),
            patch("runtime.llm.providers.ollama_provider.ollama_generate", return_value="hello there"),
        ):
            response = OllamaProvider().generate(LLMRequest(prompt="hi"))

        assert response.text == "hello there"
        assert response.provider == "ollama"
        assert response.model == "qwen3:4b"

    def test_request_model_override_is_used(self):
        from runtime.llm import LLMRequest
        from runtime.llm.providers.ollama_provider import OllamaProvider

        captured = {}

        def fake_generate(base_url, model, prompt, **kwargs):
            captured["model"] = model
            return "ok"

        with (
            patch("runtime.llm.providers.ollama_provider.discover_ollama_endpoint", return_value="http://x"),
            patch("runtime.llm.providers.ollama_provider.discover_default_model", return_value="default-model"),
            patch("runtime.llm.providers.ollama_provider.ollama_generate", side_effect=fake_generate),
        ):
            OllamaProvider().generate(LLMRequest(prompt="hi", model="custom-model"))

        assert captured["model"] == "custom-model"

    def test_ollama_error_becomes_llm_provider_unavailable_error(self):
        from runtime.llm import LLMProviderUnavailableError, LLMRequest
        from runtime.llm.providers.ollama_provider import OllamaProvider
        from runtime.ollama import OllamaUnreachableError

        with patch(
            "runtime.llm.providers.ollama_provider.discover_ollama_endpoint", side_effect=OllamaUnreachableError("down")
        ):
            try:
                OllamaProvider().generate(LLMRequest(prompt="hi"))
                raised = None
            except LLMProviderUnavailableError as e:
                raised = e
        assert raised is not None
        assert "down" in str(raised)
