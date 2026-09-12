"""Tests for runtime.llm.providers.deepseek_provider.DeepSeekProvider.

Mirrors tests/llm/test_openrouter_provider.py's structure exactly -- same
provider contract, same error taxonomy, no real network calls
(urllib.request.urlopen mocked at the module boundary).
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
        from runtime.llm.providers.deepseek_provider import DeepSeekProvider

        assert DeepSeekProvider(api_key="sk-test").is_available() is True

    def test_false_without_api_key(self):
        from runtime.llm.providers.deepseek_provider import DeepSeekProvider

        with patch.dict("os.environ", {}, clear=True):
            assert DeepSeekProvider(api_key=None).is_available() is False


class TestModelAndEndpointConfiguration:
    def test_defaults_to_deepseek_chat_with_no_config(self):
        from runtime.llm.providers.deepseek_provider import DeepSeekProvider

        with patch.dict("os.environ", {}, clear=True):
            provider = DeepSeekProvider(api_key="sk-test")
            assert provider._default_model == "deepseek-chat"
            assert provider._base_url == "https://api.deepseek.com/v1"

    def test_deepseek_model_env_var_selects_the_model(self):
        from runtime.llm.providers.deepseek_provider import DeepSeekProvider

        with patch.dict("os.environ", {"DEEPSEEK_MODEL": "deepseek-reasoner"}, clear=True):
            provider = DeepSeekProvider(api_key="sk-test")
            assert provider._default_model == "deepseek-reasoner"

    def test_base_url_env_var_overrides_the_default_endpoint(self):
        from runtime.llm.providers.deepseek_provider import DeepSeekProvider

        with patch.dict("os.environ", {"DEEPSEEK_BASE_URL": "https://proxy.internal/v1"}, clear=True):
            provider = DeepSeekProvider(api_key="sk-test")
            assert provider._base_url == "https://proxy.internal/v1"

    def test_explicit_constructor_args_win_over_env_vars(self):
        from runtime.llm.providers.deepseek_provider import DeepSeekProvider

        with patch.dict("os.environ", {"DEEPSEEK_MODEL": "deepseek-reasoner"}, clear=True):
            provider = DeepSeekProvider(api_key="sk-test", default_model="deepseek-chat")
            assert provider._default_model == "deepseek-chat"

    def test_request_model_wins_over_both_env_var_and_default(self):
        from runtime.llm import LLMRequest
        from runtime.llm.providers.deepseek_provider import DeepSeekProvider

        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data)
            return _FakeHTTPResponse({"choices": [{"message": {"content": "ok"}}], "model": "deepseek-reasoner"})

        with (
            patch.dict("os.environ", {"DEEPSEEK_MODEL": "deepseek-chat"}, clear=True),
            patch("urllib.request.urlopen", side_effect=fake_urlopen),
        ):
            DeepSeekProvider(api_key="sk-test").generate(LLMRequest(prompt="hi", model="deepseek-reasoner"))

        assert captured["body"]["model"] == "deepseek-reasoner"


class TestGenerate:
    def test_no_api_key_raises_provider_unavailable(self):
        from runtime.llm import LLMProviderUnavailableError, LLMRequest
        from runtime.llm.providers.deepseek_provider import DeepSeekProvider

        with patch.dict("os.environ", {}, clear=True):
            provider = DeepSeekProvider(api_key=None)
            try:
                provider.generate(LLMRequest(prompt="hi"))
                raised = False
            except LLMProviderUnavailableError:
                raised = True
        assert raised

    def test_success_parses_response(self):
        from runtime.llm import LLMRequest
        from runtime.llm.providers.deepseek_provider import DeepSeekProvider

        payload = {
            "choices": [{"message": {"content": "hello from deepseek"}}],
            "model": "deepseek-chat",
            "usage": {"total_tokens": 42},
        }
        with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(payload)):
            response = DeepSeekProvider(api_key="sk-test").generate(LLMRequest(prompt="hi"))

        assert response.text == "hello from deepseek"
        assert response.provider == "deepseek"
        assert response.model == "deepseek-chat"
        assert response.tokens_estimated == 42

    def test_request_sends_bearer_authorization_header(self):
        """The bug this provider exists to fix: news.py's hand-rolled call
        never sent this header at all, so it would 401 against DeepSeek's
        real cloud API every time."""
        from runtime.llm import LLMRequest
        from runtime.llm.providers.deepseek_provider import DeepSeekProvider

        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["headers"] = dict(req.headers)
            return _FakeHTTPResponse({"choices": [{"message": {"content": "ok"}}], "model": "deepseek-chat"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            DeepSeekProvider(api_key="sk-my-real-key").generate(LLMRequest(prompt="hi"))

        assert captured["headers"]["Authorization"] == "Bearer sk-my-real-key"

    def test_request_hits_configured_base_url(self):
        from runtime.llm import LLMRequest
        from runtime.llm.providers.deepseek_provider import DeepSeekProvider

        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            return _FakeHTTPResponse({"choices": [{"message": {"content": "ok"}}], "model": "deepseek-chat"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            DeepSeekProvider(api_key="sk-test", base_url="https://proxy.internal/v1").generate(
                LLMRequest(prompt="hi")
            )

        assert captured["url"] == "https://proxy.internal/v1/chat/completions"

    def test_max_tokens_and_temperature_forwarded(self):
        from runtime.llm import LLMRequest
        from runtime.llm.providers.deepseek_provider import DeepSeekProvider

        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data)
            return _FakeHTTPResponse({"choices": [{"message": {"content": "ok"}}], "model": "m"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            DeepSeekProvider(api_key="sk-test").generate(LLMRequest(prompt="hi", max_tokens=50, temperature=0.2))

        assert captured["body"]["max_tokens"] == 50
        assert captured["body"]["temperature"] == 0.2

    def test_network_error_becomes_provider_unavailable(self):
        from runtime.llm import LLMProviderUnavailableError, LLMRequest
        from runtime.llm.providers.deepseek_provider import DeepSeekProvider

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
            try:
                DeepSeekProvider(api_key="sk-test").generate(LLMRequest(prompt="hi"))
                raised = False
            except LLMProviderUnavailableError:
                raised = True
        assert raised

    def test_malformed_response_becomes_provider_unavailable(self):
        from runtime.llm import LLMProviderUnavailableError, LLMRequest
        from runtime.llm.providers.deepseek_provider import DeepSeekProvider

        with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse({"unexpected": "shape"})):
            try:
                DeepSeekProvider(api_key="sk-test").generate(LLMRequest(prompt="hi"))
                raised = False
            except LLMProviderUnavailableError:
                raised = True
        assert raised


class TestErrorTaxonomyMapping:
    def _http_error(self, code):
        return urllib.error.HTTPError(url="https://api.deepseek.com", code=code, msg="err", hdrs=None, fp=None)

    def test_401_becomes_authentication_error(self):
        from runtime.llm import LLMAuthenticationError, LLMRequest
        from runtime.llm.providers.deepseek_provider import DeepSeekProvider

        with patch("urllib.request.urlopen", side_effect=self._http_error(401)):
            try:
                DeepSeekProvider(api_key="sk-test").generate(LLMRequest(prompt="hi"))
                raised = None
            except LLMAuthenticationError as e:
                raised = e
        assert raised is not None

    def test_403_becomes_authentication_error(self):
        from runtime.llm import LLMAuthenticationError, LLMRequest
        from runtime.llm.providers.deepseek_provider import DeepSeekProvider

        with patch("urllib.request.urlopen", side_effect=self._http_error(403)):
            try:
                DeepSeekProvider(api_key="sk-test").generate(LLMRequest(prompt="hi"))
                raised = None
            except LLMAuthenticationError as e:
                raised = e
        assert raised is not None

    def test_404_becomes_model_not_found_error(self):
        from runtime.llm import LLMModelNotFoundError, LLMRequest
        from runtime.llm.providers.deepseek_provider import DeepSeekProvider

        with patch("urllib.request.urlopen", side_effect=self._http_error(404)):
            try:
                DeepSeekProvider(api_key="sk-test").generate(LLMRequest(prompt="hi"))
                raised = None
            except LLMModelNotFoundError as e:
                raised = e
        assert raised is not None

    def test_500_becomes_generic_provider_unavailable_error(self):
        from runtime.llm import LLMModelNotFoundError, LLMProviderUnavailableError, LLMRequest
        from runtime.llm.providers.deepseek_provider import DeepSeekProvider

        with patch("urllib.request.urlopen", side_effect=self._http_error(500)):
            try:
                DeepSeekProvider(api_key="sk-test").generate(LLMRequest(prompt="hi"))
                raised = None
            except LLMProviderUnavailableError as e:
                raised = e
        assert raised is not None
        assert not isinstance(raised, LLMModelNotFoundError)

    def test_timeout_error_becomes_llm_timeout_error(self):
        from runtime.llm import LLMRequest, LLMTimeoutError
        from runtime.llm.providers.deepseek_provider import DeepSeekProvider

        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            try:
                DeepSeekProvider(api_key="sk-test").generate(LLMRequest(prompt="hi"))
                raised = None
            except LLMTimeoutError as e:
                raised = e
        assert raised is not None
