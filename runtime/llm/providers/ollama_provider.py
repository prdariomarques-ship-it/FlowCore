"""OllamaProvider -- wraps runtime/ollama.py behind the LLMProvider
contract. No logic duplicated: endpoint/model discovery, warm-up,
timeout, and error classification all stay exactly as they are in
runtime/ollama.py -- this class only translates OllamaError subclasses
into the generic runtime.llm error taxonomy at the boundary, preserving
which *kind* of failure it was (auth/not-found/timeout/generic) so
callers of LLMRouter can still differentiate without ever importing
runtime.ollama themselves.
"""

from __future__ import annotations

import time

from runtime.llm.models import (
    LLMAuthenticationError,
    LLMModelNotFoundError,
    LLMProviderUnavailableError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
)
from runtime.llm.provider import LLMProvider
from runtime.ollama import (
    OllamaError,
    OllamaModelLoadTimeoutError,
    OllamaModelNotInstalledError,
    OllamaSubscriptionRequiredError,
    discover_default_model,
    discover_ollama_endpoint,
)
from runtime.ollama import generate as ollama_generate

__all__ = ["OllamaProvider"]


class OllamaProvider(LLMProvider):
    name = "ollama"

    def is_available(self) -> bool:
        try:
            discover_ollama_endpoint()
            return True
        except OllamaError:
            return False

    def generate(self, request: LLMRequest) -> LLMResponse:
        start = time.monotonic()
        try:
            base_url = discover_ollama_endpoint()
            model = (request.metadata or {}).get("selected_model") or request.model or discover_default_model()
            kwargs = {"timeout": request.timeout} if request.timeout is not None else {}
            text = ollama_generate(base_url, model, request.prompt, **kwargs)
        except OllamaSubscriptionRequiredError as e:
            raise LLMAuthenticationError(str(e)) from e
        except OllamaModelNotInstalledError as e:
            raise LLMModelNotFoundError(str(e)) from e
        except OllamaModelLoadTimeoutError as e:
            raise LLMTimeoutError(str(e)) from e
        except OllamaError as e:
            raise LLMProviderUnavailableError(str(e)) from e
        latency_ms = (time.monotonic() - start) * 1000
        return LLMResponse(text=text, provider=self.name, model=model, latency_ms=latency_ms, tokens_estimated=None)
