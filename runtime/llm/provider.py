"""LLMProvider -- the contract every backend (local or cloud) implements.

Sync, blocking by design: mirrors runtime/ollama.py's own generate()
shape (network I/O, no async client needed for a single request/response
call). Callers that need to stay responsive (FastAPI/MCP event loops)
wrap a call in asyncio.to_thread(), exactly as service.ask() already
does for runtime/ollama.py today -- the Router does not change that
convention, it only replaces *which* function gets wrapped.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from runtime.llm.models import LLMRequest, LLMResponse

__all__ = ["LLMProvider"]


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def is_available(self) -> bool:
        """Cheap, synchronous reachability/configuration check -- no
        generation attempted. Used by the Router to filter the policy's
        candidate list before spending a real call on a provider that
        obviously can't serve it (e.g. no API key configured)."""

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        """Raises LLMProviderUnavailableError (or a subclass) on any
        failure -- never a provider-specific exception type."""
