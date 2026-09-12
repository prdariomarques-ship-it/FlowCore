"""DARIUS OSS Asynchronous Job and Background Execution Subsystem.

Provides non-blocking job dispatching, prioritized queues, timeout controls,
worker pooling, and snapshot pre-computation caching.
"""

from __future__ import annotations

from darius.jobs.cache import CacheEntry, SnapshotCache
from darius.jobs.dispatcher import (
    AsyncJobDispatcher,
    JobPriority,
    JobRecord,
    JobStatus,
)

__all__ = [
    "AsyncJobDispatcher",
    "JobPriority",
    "JobRecord",
    "JobStatus",
    "SnapshotCache",
    "CacheEntry",
]
