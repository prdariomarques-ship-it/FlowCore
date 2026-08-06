"""Tests for runtime.llm.providers.openrouter_provider.OpenRouterProvider.

No real network calls — urllib.request.urlopen is mocked at the module
boundary.
"""

from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _FakeHTTPResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestIsAvailable:
    def test_true_when_api_key_configured(self):
        from runtime.llm.providers.openrouter_provider import OpenRouterProvider

        assert OpenRouterProvider(api_key="sk-test").is_available() is True

    def test_false_without_api_key(self):
        from runtime.llm.providers.openrouter_provider import OpenRouterProvider

        with patch.dict("os.environ", {}, clear=True):
            assert OpenRouterProvider(api_key=None).is_available() is False


class TestGenerate:
    def test_no_api_key_raises_provider_unavailable(self):
        from runtime.llm import LLMProviderUnavailableError, LLMRequest
        from runtime.llm.providers.openrouter_provider import OpenRouterProvider

        with patch.dict("os.environ", {}, clear=True):
            provider = OpenRouterProvider(api_key=None)
            try:
                provider.generate(LLMRequest(prompt="hi"))
                raised = False
            except LLMProviderUnavailableError:
                raised = True
        assert raised

    def test_success_parses_response(self):
        from runtime.llm import LLMRequest
        from runtime.llm.providers.openrouter_provider import OpenRouterProvider

        payload = {
            "choices": [{"message": {"content": "hello from openrouter"}}],
            "model": "openrouter/auto",
            "usage": {"total_tokens": 42},
        }
        with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(payload)):
            response = OpenRouterProvider(api_key="sk-test").generate(LLMRequest(prompt="hi"))

        assert response.text == "hello from openrouter"
        assert response.provider == "openrouter"
        assert response.model == "openrouter/auto"
        assert response.tokens_estimated == 42

    def test_request_model_is_sent(self):
        from runtime.llm import LLMRequest
        from runtime.llm.providers.openrouter_provider import OpenRouterProvider

        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data)
            return _FakeHTTPResponse({"choices": [{"message": {"content": "ok"}}], "model": "gpt-4o"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            OpenRouterProvider(api_key="sk-test").generate(LLMRequest(prompt="hi", model="gpt-4o"))

        assert captured["body"]["model"] == "gpt-4o"
        assert captured["body"]["messages"] == [{"role": "user", "content": "hi"}]

    def test_network_error_becomes_provider_unavailable(self):
        from runtime.llm import LLMProviderUnavailableError, LLMRequest
        from runtime.llm.providers.openrouter_provider import OpenRouterProvider

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
            try:
                OpenRouterProvider(api_key="sk-test").generate(LLMRequest(prompt="hi"))
                raised = False
            except LLMProviderUnavailableError:
                raised = True
        assert raised

    def test_malformed_response_becomes_provider_unavailable(self):
        from runtime.llm import LLMProviderUnavailableError, LLMRequest
        from runtime.llm.providers.openrouter_provider import OpenRouterProvider

        with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse({"unexpected": "shape"})):
            try:
                OpenRouterProvider(api_key="sk-test").generate(LLMRequest(prompt="hi"))
                raised = False
            except LLMProviderUnavailableError:
                raised = True
        assert raised

    def test_max_tokens_and_temperature_forwarded(self):
        from runtime.llm import LLMRequest
        from runtime.llm.providers.openrouter_provider import OpenRouterProvider

        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data)
            return _FakeHTTPResponse({"choices": [{"message": {"content": "ok"}}], "model": "m"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            OpenRouterProvider(api_key="sk-test").generate(LLMRequest(prompt="hi", max_tokens=50, temperature=0.2))

        assert captured["body"]["max_tokens"] == 50
        assert captured["body"]["temperature"] == 0.2
