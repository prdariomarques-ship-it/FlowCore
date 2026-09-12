"""Tests for AsyncJobDispatcher, Priority Scheduling, and SnapshotCache."""

from __future__ import annotations

import asyncio
import time

import pytest

from darius.jobs.cache import SnapshotCache
from darius.jobs.dispatcher import (
    AsyncJobDispatcher,
    JobPriority,
    JobStatus,
)


class TestSnapshotCache:
    def test_basic_set_and_get(self):
        cache = SnapshotCache(default_ttl_seconds=60.0)
        cache.set("key1", {"data": 123})

        assert cache.get("key1") == {"data": 123}
        assert cache.get("nonexistent") is None
        assert cache.hits == 1
        assert cache.misses == 1

    def test_ttl_expiration(self):
        cache = SnapshotCache(default_ttl_seconds=0.05)
        cache.set("short_lived", "alive")

        assert cache.get("short_lived") == "alive"
        time.sleep(0.06)
        assert cache.get("short_lived") is None
        assert cache.evictions == 1

    def test_delete_and_clear(self):
        cache = SnapshotCache()
        cache.set("k1", "v1")
        cache.set("k2", "v2")

        assert cache.delete("k1") is True
        assert cache.get("k1") is None
        assert cache.delete("k1") is False

        cache.clear()
        assert cache.get("k2") is None

    @pytest.mark.asyncio
    async def test_get_or_compute_stampede_protection(self):
        cache = SnapshotCache(default_ttl_seconds=60.0)
        compute_call_count = 0

        async def heavy_computation():
            nonlocal compute_call_count
            compute_call_count += 1
            await asyncio.sleep(0.05)
            return {"heavy": "result"}

        # Simulate 5 concurrent requests arriving at the same instant
        tasks = [asyncio.create_task(cache.get_or_compute("heavy_key", heavy_computation)) for _ in range(5)]
        results = await asyncio.gather(*tasks)

        for res in results:
            assert res == {"heavy": "result"}

        # Heavy computation must be called EXACTLY once thanks to lock
        assert compute_call_count == 1
        stats = cache.get_stats()
        assert stats["entries_count"] == 1
        assert stats["hits"] >= 4

    def test_cache_metrics(self):
        cache = SnapshotCache()
        cache.set("k", "v")
        cache.get("k")  # hit
        cache.get("missing")  # miss

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_ratio"] == 0.5


class TestAsyncJobDispatcher:
    @pytest.mark.asyncio
    async def test_prioritization_critical_before_batch(self):
        dispatcher = AsyncJobDispatcher(max_workers=1)
        execution_order: list[str] = []

        async def record_task(name: str):
            execution_order.append(name)

        # Enqueue BATCH first, then CRITICAL, before starting workers
        dispatcher.submit("batch_job", record_task, "batch", priority=JobPriority.BATCH)
        dispatcher.submit("critical_job", record_task, "critical", priority=JobPriority.CRITICAL)

        await dispatcher.start()
        try:
            # Allow workers to drain the queue
            for _ in range(20):
                if len(execution_order) == 2:
                    break
                await asyncio.sleep(0.05)

            assert execution_order == ["critical", "batch"]
        finally:
            await dispatcher.stop()

    @pytest.mark.asyncio
    async def test_concurrency_worker_limit(self):
        dispatcher = AsyncJobDispatcher(max_workers=2)
        active_count = 0
        max_active_observed = 0

        async def monitored_task():
            nonlocal active_count, max_active_observed
            active_count += 1
            if active_count > max_active_observed:
                max_active_observed = active_count
            await asyncio.sleep(0.05)
            active_count -= 1
            return "done"

        await dispatcher.start()
        try:
            job_ids = [dispatcher.submit(f"task_{i}", monitored_task) for i in range(4)]

            for jid in job_ids:
                record = await dispatcher.wait_for_job(jid, timeout=2.0)
                assert record.status == JobStatus.COMPLETED

            assert max_active_observed <= 2
        finally:
            await dispatcher.stop()

    @pytest.mark.asyncio
    async def test_job_timeout(self):
        dispatcher = AsyncJobDispatcher(max_workers=1)

        async def hanging_task():
            await asyncio.sleep(1.0)
            return "too late"

        await dispatcher.start()
        try:
            job_id = dispatcher.submit("hanging", hanging_task, timeout_seconds=0.05)
            record = await dispatcher.wait_for_job(job_id, timeout=2.0)

            assert record.status == JobStatus.TIMEOUT
            assert "timed out" in (record.error or "")
        finally:
            await dispatcher.stop()

    @pytest.mark.asyncio
    async def test_job_retry_success(self):
        dispatcher = AsyncJobDispatcher(max_workers=1)
        attempts = 0

        async def flaky_task():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise ValueError("Transient network error")
            return "recovered"

        await dispatcher.start()
        try:
            job_id = dispatcher.submit("flaky", flaky_task, max_retries=2)
            record = await dispatcher.wait_for_job(job_id, timeout=2.0)

            assert record.status == JobStatus.COMPLETED
            assert record.result == "recovered"
            assert record.retry_count == 1
        finally:
            await dispatcher.stop()

    @pytest.mark.asyncio
    async def test_job_permanent_failure(self):
        dispatcher = AsyncJobDispatcher(max_workers=1)

        async def broken_task():
            raise RuntimeError("Fatal unrecoverable error")

        await dispatcher.start()
        try:
            job_id = dispatcher.submit("broken", broken_task, max_retries=1)
            record = await dispatcher.wait_for_job(job_id, timeout=2.0)

            assert record.status == JobStatus.FAILED
            assert "Fatal unrecoverable error" in (record.error or "")
            assert record.retry_count == 1
        finally:
            await dispatcher.stop()

    @pytest.mark.asyncio
    async def test_job_cancellation(self):
        dispatcher = AsyncJobDispatcher(max_workers=1)

        async def slow_task():
            await asyncio.sleep(0.5)

        # Submit before starting
        job_id = dispatcher.submit("queued_task", slow_task)
        assert dispatcher.cancel_job(job_id) is True

        record = dispatcher.get_job(job_id)
        assert record is not None
        assert record.status == JobStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_metrics_reporting(self):
        dispatcher = AsyncJobDispatcher(max_workers=2)

        async def fast_task():
            return 42

        await dispatcher.start()
        try:
            job_id = dispatcher.submit("fast", fast_task)
            await dispatcher.wait_for_job(job_id, timeout=2.0)

            metrics = dispatcher.get_metrics()
            assert metrics["completed"] == 1
            assert metrics["max_workers"] == 2
            assert metrics["failed"] == 0
        finally:
            await dispatcher.stop()
