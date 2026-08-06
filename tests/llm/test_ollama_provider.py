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

    def test_unreachable_becomes_llm_provider_unavailable_error(self):
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


class TestErrorTaxonomyMapping:
    """Each OllamaError subclass must map to the matching provider-
    agnostic runtime.llm error, so callers of LLMRouter can differentiate
    without ever importing runtime.ollama."""

    def test_subscription_required_becomes_authentication_error(self):
        from runtime.llm import LLMAuthenticationError, LLMRequest
        from runtime.llm.providers.ollama_provider import OllamaProvider
        from runtime.ollama import OllamaSubscriptionRequiredError

        with (
            patch("runtime.llm.providers.ollama_provider.discover_ollama_endpoint", return_value="http://x"),
            patch("runtime.llm.providers.ollama_provider.discover_default_model", return_value="m"),
            patch(
                "runtime.llm.providers.ollama_provider.ollama_generate",
                side_effect=OllamaSubscriptionRequiredError("needs subscription"),
            ),
        ):
            try:
                OllamaProvider().generate(LLMRequest(prompt="hi"))
                raised = None
            except LLMAuthenticationError as e:
                raised = e
        assert raised is not None

    def test_model_not_installed_becomes_model_not_found_error(self):
        from runtime.llm import LLMModelNotFoundError, LLMRequest
        from runtime.llm.providers.ollama_provider import OllamaProvider
        from runtime.ollama import OllamaModelNotInstalledError

        with (
            patch("runtime.llm.providers.ollama_provider.discover_ollama_endpoint", return_value="http://x"),
            patch("runtime.llm.providers.ollama_provider.discover_default_model", return_value="m"),
            patch(
                "runtime.llm.providers.ollama_provider.ollama_generate",
                side_effect=OllamaModelNotInstalledError("not installed"),
            ),
        ):
            try:
                OllamaProvider().generate(LLMRequest(prompt="hi"))
                raised = None
            except LLMModelNotFoundError as e:
                raised = e
        assert raised is not None

    def test_model_load_timeout_becomes_llm_timeout_error(self):
        from runtime.llm import LLMRequest, LLMTimeoutError
        from runtime.llm.providers.ollama_provider import OllamaProvider
        from runtime.ollama import OllamaModelLoadTimeoutError

        with (
            patch("runtime.llm.providers.ollama_provider.discover_ollama_endpoint", return_value="http://x"),
            patch("runtime.llm.providers.ollama_provider.discover_default_model", return_value="m"),
            patch(
                "runtime.llm.providers.ollama_provider.ollama_generate",
                side_effect=OllamaModelLoadTimeoutError("too slow"),
            ),
        ):
            try:
                OllamaProvider().generate(LLMRequest(prompt="hi"))
                raised = None
            except LLMTimeoutError as e:
                raised = e
        assert raised is not None

    def test_all_mapped_errors_are_still_llm_error(self):
        """Every specific subclass remains catchable via the base
        LLMError -- a caller that doesn't care about the distinction
        loses nothing."""
        from runtime.llm import LLMAuthenticationError, LLMError, LLMModelNotFoundError, LLMTimeoutError

        assert issubclass(LLMAuthenticationError, LLMError)
        assert issubclass(LLMModelNotFoundError, LLMError)
        assert issubclass(LLMTimeoutError, LLMError)
