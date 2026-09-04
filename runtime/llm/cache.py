"""CacheBackend -- optional response caching, keyed by a hash of the
request. NullCache (default) never caches -- correct default, since
most FlowCore LLM calls are either RAG-grounded (context changes call
to call) or narrating a live-recomputed DecisionReport (stale-narrative
risk). InMemoryTTLCache is provided as a real, working option for
callers that explicitly want it (e.g. a future high-volume, low-
variance prompt), not wired in by default anywhere.
"""

from __future__ import annotations

import hashlib
import time
from abc import ABC, abstractmethod

from runtime.llm.models import LLMRequest, LLMResponse

__all__ = ["CacheBackend", "NullCache", "InMemoryTTLCache", "cache_key_for"]


def cache_key_for(request: LLMRequest) -> str:
    raw = f"{request.model}|{request.prompt}|{request.max_tokens}|{request.temperature}"
    return hashlib.sha256(raw.encode()).hexdigest()


class CacheBackend(ABC):
    @abstractmethod
    def get(self, key: str) -> LLMResponse | None: ...

    @abstractmethod
    def set(self, key: str, response: LLMResponse) -> None: ...


class NullCache(CacheBackend):
    def get(self, key: str) -> LLMResponse | None:
        return None

    def set(self, key: str, response: LLMResponse) -> None:
        pass


class InMemoryTTLCache(CacheBackend):
    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[float, LLMResponse]] = {}

    def get(self, key: str) -> LLMResponse | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, response = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return response

    def set(self, key: str, response: LLMResponse) -> None:
        self._store[key] = (time.monotonic() + self._ttl, response)
