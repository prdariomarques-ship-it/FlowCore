"""Snapshot Cache with TTL and Stampede Protection for Heavy Engine Results."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Generic, TypeVar

T = TypeVar("T")


@dataclass
class CacheEntry:
    """Stored cache item with timestamp and expiry."""

    key: str
    value: Any
    created_at: float
    expires_at: float

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class SnapshotCache:
    """Thread-safe and async-safe TTL cache with cache-stampede (thundering herd) protection."""

    def __init__(self, default_ttl_seconds: float = 300.0) -> None:
        self.default_ttl = default_ttl_seconds
        self._store: dict[str, CacheEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._master_lock = asyncio.Lock()
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def get(self, key: str) -> Any | None:
        """Retrieve a cached value if present and unexpired."""
        entry = self._store.get(key)
        if entry is None:
            self.misses += 1
            return None

        if entry.is_expired:
            self.misses += 1
            self._store.pop(key, None)
            self.evictions += 1
            return None

        self.hits += 1
        return entry.value

    def get_entry(self, key: str) -> CacheEntry | None:
        """Retrieve the raw CacheEntry for introspection."""
        entry = self._store.get(key)
        if entry and not entry.is_expired:
            return entry
        return None

    def set(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        """Store a value in cache with a defined TTL."""
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        now = time.time()
        self._store[key] = CacheEntry(
            key=key,
            value=value,
            created_at=now,
            expires_at=now + ttl,
        )

    def delete(self, key: str) -> bool:
        """Remove an item from cache."""
        return self._store.pop(key, None) is not None

    def clear(self) -> None:
        """Purge all cached items."""
        self._store.clear()
        self._locks.clear()

    async def _get_lock(self, key: str) -> asyncio.Lock:
        """Acquire or create an atomic lock for a specific key."""
        async with self._master_lock:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]

    async def get_or_compute(
        self,
        key: str,
        compute_fn: Callable[[], Awaitable[T]],
        ttl_seconds: float | None = None,
    ) -> T:
        """Return cached value, or compute it atomically preventing duplicate background work."""
        cached = self.get(key)
        if cached is not None:
            return cached

        # Protect against thundering herd: only one coroutine computes
        key_lock = await self._get_lock(key)
        async with key_lock:
            # Double-checked locking
            cached_after_lock = self.get(key)
            if cached_after_lock is not None:
                return cached_after_lock

            computed = await compute_fn()
            self.set(key, computed, ttl_seconds=ttl_seconds)
            return computed

    def get_stats(self) -> dict[str, Any]:
        """Return operational metrics for cache efficiency."""
        total_requests = self.hits + self.misses
        hit_ratio = (self.hits / total_requests) if total_requests > 0 else 0.0
        return {
            "entries_count": len(self._store),
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "hit_ratio": round(hit_ratio, 4),
        }
