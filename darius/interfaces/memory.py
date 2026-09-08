"""Memory Adapter Protocol and Data Models for DARIUS OSS."""

from __future__ import annotations

import time
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class MemoryEntry(BaseModel):
    """Atomic memory unit across working, episodic, and semantic tiers."""

    id: str
    content: str
    category: Literal["working", "episodic", "semantic"]
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)


class MemorySearchResult(BaseModel):
    """Ranked search result retrieved from memory storage."""

    entry: MemoryEntry
    score: float = 1.0


@runtime_checkable
class MemoryAdapter(Protocol):
    """Port interface for hierarchical agent memory storage and retrieval."""

    async def store(self, entry: MemoryEntry) -> bool:
        """Persist a memory entry to the appropriate storage tier."""
        ...

    async def retrieve(self, query: str, limit: int = 5, **kwargs: Any) -> list[MemoryEntry]:
        """Query memory by keyword or criteria."""
        ...

    async def search_semantic(self, query: str, limit: int = 5, **kwargs: Any) -> list[MemorySearchResult]:
        """Query semantic memory using vector embeddings."""
        ...

    async def clear_working_memory(self, session_id: str) -> None:
        """Purge temporary working scratchpad memory for an active session."""
        ...

    async def delete(self, entry_id: str) -> bool:
        """Delete an individual memory record by ID."""
        ...
