"""OpenRouterProvider -- the default cloud backend. OpenRouter itself is
a meta-provider (one OpenAI-compatible API in front of GPT/Claude/
Gemini/DeepSeek/many others) -- implementing this one provider, with the
model chosen via LLMRequest.model, is what satisfies "the rest of
FlowCore must never know whether the request is executed by Claude,
DeepSeek, OpenAI, Gemini, ..." without a separate provider class per
cloud vendor.

Stdlib-only (urllib), matching runtime/ollama.py's own style -- no new
HTTP client dependency.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from runtime.llm.models import LLMProviderUnavailableError, LLMRequest, LLMResponse
from runtime.llm.provider import LLMProvider

__all__ = ["OpenRouterProvider"]

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_MODEL = "openrouter/auto"  # OpenRouter's own cost/quality auto-router


class OpenRouterProvider(LLMProvider):
    name = "openrouter"

    def __init__(self, api_key: str | None = None, default_model: str = _DEFAULT_MODEL) -> None:
        self._api_key = api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY")
        self._default_model = default_model

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
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
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
