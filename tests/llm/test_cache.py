"""Tests for runtime.llm.cache."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _response(text="hi"):
    from runtime.llm import LLMResponse

    return LLMResponse(text=text, provider="ollama", model="m", latency_ms=1.0)


class TestCacheKeyFor:
    def test_same_request_same_key(self):
        from runtime.llm import LLMRequest
        from runtime.llm.cache import cache_key_for

        r1 = LLMRequest(prompt="hello", model="m")
        r2 = LLMRequest(prompt="hello", model="m")
        assert cache_key_for(r1) == cache_key_for(r2)

    def test_different_prompt_different_key(self):
        from runtime.llm import LLMRequest
        from runtime.llm.cache import cache_key_for

        r1 = LLMRequest(prompt="hello")
        r2 = LLMRequest(prompt="goodbye")
        assert cache_key_for(r1) != cache_key_for(r2)


class TestNullCache:
    def test_never_caches(self):
        from runtime.llm import NullCache

        c = NullCache()
        c.set("k", _response())
        assert c.get("k") is None


class TestInMemoryTTLCache:
    def test_stores_and_retrieves(self):
        from runtime.llm.cache import InMemoryTTLCache

        c = InMemoryTTLCache(ttl_seconds=60)
        resp = _response("cached text")
        c.set("k", resp)
        assert c.get("k").text == "cached text"

    def test_missing_key_returns_none(self):
        from runtime.llm.cache import InMemoryTTLCache

        assert InMemoryTTLCache().get("missing") is None

    def test_expired_entry_returns_none_and_is_evicted(self):
        from runtime.llm.cache import InMemoryTTLCache

        c = InMemoryTTLCache(ttl_seconds=0.05)
        c.set("k", _response())
        time.sleep(0.1)
        assert c.get("k") is None
        assert "k" not in c._store
