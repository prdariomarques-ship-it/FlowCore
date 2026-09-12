"""DeepSeekProvider -- native, first-class DeepSeek backend for the LLM
Router.

Before this file existed, "DeepSeek" appeared in this codebase in two
places, neither of them a real Router provider:

  1. runtime/llm/policy.py's LocalFirstPolicy.DEFAULT_ORDER lists
     "deepseek" as a name -- but no provider was ever registered under
     that name in service.py, so the policy could never actually route
     to it (ProviderRegistry.available_names() would just never contain
     it).
  2. runtime/market_intelligence/news.py has a one-off, hand-rolled call
     straight to `{ai.json's deepseek_url}/v1/chat/completions` for
     headline translation only -- and critically, that call sends no
     Authorization header at all (see api.dashboard_routes._http_json,
     which the news.py call reuses), so it would get a 401 from
     DeepSeek's real cloud API and silently fall through to Ollama
     (wrapped in a bare `except Exception: pass`).

This provider is the real thing: a proper LLMProvider implementation any
agent/engine already speaking the Router's vocabulary (LLMRequest ->
LLMResponse) can use, authenticated correctly, following the exact same
shape as OpenRouterProvider (this codebase's other cloud provider) --
same env-var configuration convention, same HTTP status -> error
taxonomy mapping, same stdlib-only (urllib) implementation.

Configuration (env-driven, matching OPENROUTER_API_KEY/OPENROUTER_MODEL):
  DEEPSEEK_API_KEY   -- required for is_available() to return True.
  DEEPSEEK_MODEL     -- defaults to "deepseek-chat" (DeepSeek-V3). Set to
                        "deepseek-reasoner" for DeepSeek-R1-class
                        reasoning, no code change needed.
  DEEPSEEK_BASE_URL  -- defaults to DeepSeek's own cloud API
                        (https://api.deepseek.com/v1). Overridable for a
                        self-hosted-compatible proxy, matching
                        ~/.flowcore/ai.json's existing "deepseek_url"
                        convention for the news.py translation path.

To make DeepSeek the Router's effective default once a key is
configured, register it before OpenRouterProvider in service.py and list
it first in FLOWCORE_LLM_PROVIDER_ORDER (see policy.py) -- this file only
adds the provider; it does not change routing order on its own.
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

__all__ = ["DeepSeekProvider"]

_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
_DEFAULT_MODEL = "deepseek-chat"


class DeepSeekProvider(LLMProvider):
    name = "deepseek"

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.getenv("DEEPSEEK_API_KEY")
        self._default_model = default_model or os.getenv("DEEPSEEK_MODEL") or _DEFAULT_MODEL
        self._base_url = (base_url or os.getenv("DEEPSEEK_BASE_URL") or _DEFAULT_BASE_URL).rstrip("/")

    def is_available(self) -> bool:
        return bool(self._api_key)

    def generate(self, request: LLMRequest) -> LLMResponse:
        if not self._api_key:
            raise LLMProviderUnavailableError("DEEPSEEK_API_KEY not configured")

        model = request.model or self._default_model
        payload: dict = {"model": model, "messages": [{"role": "user", "content": request.prompt}]}
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        req = urllib.request.Request(
            f"{self._base_url}/chat/completions",
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
                raise LLMAuthenticationError(f"DeepSeek rejected the request ({e.code}): {e}") from e
            if e.code == 404:
                raise LLMModelNotFoundError(f"DeepSeek model not found ({e.code}): {model}") from e
            raise LLMProviderUnavailableError(f"DeepSeek request failed ({e.code}): {e}") from e
        except TimeoutError as e:
            raise LLMTimeoutError(f"DeepSeek request timed out: {e}") from e
        except (urllib.error.URLError, ValueError) as e:
            raise LLMProviderUnavailableError(f"DeepSeek request failed: {e}") from e

        latency_ms = (time.monotonic() - start) * 1000
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMProviderUnavailableError(f"DeepSeek returned an unexpected response shape: {e}") from e

        usage = data.get("usage") or {}
        return LLMResponse(
            text=text,
            provider=self.name,
            model=data.get("model", model),
            latency_ms=latency_ms,
            tokens_estimated=usage.get("total_tokens"),
        )
