"""OpenRouterProvider -- the default cloud backend. OpenRouter itself is
a meta-provider (one OpenAI-compatible API in front of GPT/Claude/
Gemini/DeepSeek/many others) -- implementing this one provider, with the
model chosen via LLMRequest.model, is what satisfies "the rest of
FlowCore must never know whether the request is executed by Claude,
DeepSeek, OpenAI, Gemini, ..." without a separate provider class per
cloud vendor.

Stdlib-only (urllib), matching runtime/ollama.py's own style -- no new
HTTP client dependency.

Configuration is entirely environment-driven, same convention as
runtime/ollama.py's FLOWCORE_OLLAMA/FLOWCORE_MODEL:
  OPENROUTER_API_KEY  -- required for is_available() to return True.
  OPENROUTER_MODEL    -- which underlying model OpenRouter routes to.
                         Switching backends (e.g. to DeepSeek) is a pure
                         config change, no code change:
                             OPENROUTER_MODEL=deepseek/deepseek-v4-flash
                             OPENROUTER_MODEL=anthropic/claude-sonnet-4
                             OPENROUTER_MODEL=openai/gpt-5.5
                         Falls back to "openrouter/auto" (OpenRouter's own
                         cost/quality auto-router) when unset. A caller can
                         still override per-request via LLMRequest.model,
                         which always wins over both the env var and the
                         constructor default.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from runtime.llm.models import (
    LLMAuthenticationError,
    LLMModelNotFoundError,
    LLMProviderUnavailableError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
)
from runtime.llm.provider import LLMProvider

__all__ = ["OpenRouterProvider"]

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_AUTO_MODEL = "openrouter/auto"  # OpenRouter's own cost/quality auto-router


class OpenRouterProvider(LLMProvider):
    name = "openrouter"

    def __init__(self, api_key: str | None = None, default_model: str | None = None) -> None:
        self._api_key = api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY")
        self._default_model = default_model or os.getenv("OPENROUTER_MODEL") or _AUTO_MODEL

    def is_available(self) -> bool:
        return bool(self._api_key)

    def generate(self, request: LLMRequest) -> LLMResponse:
        if not self._api_key:
            raise LLMProviderUnavailableError("OPENROUTER_API_KEY not configured")

        model = request.model or self._default_model
        payload: dict = {"model": model, "messages": [{"role": "user", "content": request.prompt}]}
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        req = urllib.request.Request(
            _API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        start = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=request.timeout or 60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise LLMAuthenticationError(f"OpenRouter rejected the request ({e.code}): {e}") from e
            if e.code == 404:
                raise LLMModelNotFoundError(f"OpenRouter model not found ({e.code}): {model}") from e
            raise LLMProviderUnavailableError(f"OpenRouter request failed ({e.code}): {e}") from e
        except TimeoutError as e:
            raise LLMTimeoutError(f"OpenRouter request timed out: {e}") from e
        except (urllib.error.URLError, ValueError) as e:
            raise LLMProviderUnavailableError(f"OpenRouter request failed: {e}") from e

        latency_ms = (time.monotonic() - start) * 1000
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMProviderUnavailableError(f"OpenRouter returned an unexpected response shape: {e}") from e

        usage = data.get("usage") or {}
        return LLMResponse(
            text=text,
            provider=self.name,
            model=data.get("model", model),
            latency_ms=latency_ms,
            tokens_estimated=usage.get("total_tokens"),
        )
