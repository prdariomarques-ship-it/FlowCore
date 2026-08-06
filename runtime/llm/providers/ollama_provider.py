"""OllamaProvider -- wraps runtime/ollama.py behind the LLMProvider
contract. No logic duplicated: endpoint/model discovery, warm-up,
timeout, and error classification all stay exactly as they are in
runtime/ollama.py (used directly by service.ask()/Chat too) -- this
class only translates OllamaError subclasses into LLMProviderUnavailableError
at the boundary.
"""

from __future__ import annotations

import time

from runtime.llm.models import LLMProviderUnavailableError, LLMRequest, LLMResponse
from runtime.llm.provider import LLMProvider
from runtime.ollama import OllamaError, discover_default_model, discover_ollama_endpoint
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
            model = request.model or discover_default_model()
            kwargs = {"timeout": request.timeout} if request.timeout is not None else {}
            text = ollama_generate(base_url, model, request.prompt, **kwargs)
        except OllamaError as e:
            raise LLMProviderUnavailableError(str(e)) from e
        latency_ms = (time.monotonic() - start) * 1000
        return LLMResponse(text=text, provider=self.name, model=model, latency_ms=latency_ms, tokens_estimated=None)
