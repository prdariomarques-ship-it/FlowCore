"""Asynchronous Background Job Dispatcher with Priority Scheduling and Concurrency Control."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any

logger = logging.getLogger(__name__)


class JobPriority(IntEnum):
    """Execution priority levels (lower number executes first)."""

    CRITICAL = 1
    HIGH = 2
    DEFAULT = 3
    BATCH = 4
    MONITORING = 5


class JobStatus(str, Enum):
    """Lifecycle states of an asynchronous background job."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"


@dataclass
class JobRecord:
    """Historical and execution metadata for a job."""

    id: str
    name: str
    priority: JobPriority
    status: JobStatus = JobStatus.QUEUED
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    result: Any = None
    error: str | None = None
    execution_ms: int = 0
    retry_count: int = 0
    max_retries: int = 0
    timeout_seconds: float = 30.0


@dataclass
class _JobItem:
    record: JobRecord
    fn: Callable[..., Awaitable[Any]]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


class AsyncJobDispatcher:
    """Non-blocking background job dispatcher with priority scheduling, worker pooling, and retry logic."""

    def __init__(self, max_workers: int = 4) -> None:
        self.max_workers = max_workers
        self._queue: asyncio.PriorityQueue[tuple[int, float, str]] = asyncio.PriorityQueue()
        self._jobs: dict[str, _JobItem] = {}
        self._worker_tasks: list[asyncio.Task[None]] = []
        self._running_tasks: dict[str, asyncio.Task[Any]] = {}
        self._running = False
        self._total_completed = 0
        self._total_failed = 0
        self._total_timeouts = 0
        self._total_cancelled = 0
        self._total_execution_ms = 0

    @property
    def is_running(self) -> bool:
        return self._running

    def submit(
        self,
        name: str,
        fn: Callable[..., Awaitable[Any]],
        *args: Any,
        priority: JobPriority = JobPriority.DEFAULT,
        timeout_seconds: float = 30.0,
        max_retries: int = 0,
        **kwargs: Any,
    ) -> str:
        """Submit a coroutine for execution in the background."""
        job_id = str(uuid.uuid4())
        record = JobRecord(
            id=job_id,
            name=name,
            priority=priority,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
        item = _JobItem(record=record, fn=fn, args=args, kwargs=kwargs)
        self._jobs[job_id] = item

        # PriorityQueue sorts by tuple: (priority_int, timestamp, job_id)
        self._queue.put_nowait((int(priority), record.created_at, job_id))
        logger.debug("Submitted job '%s' (%s) with priority %s", name, job_id, priority.name)
        return job_id

    def get_job(self, job_id: str) -> JobRecord | None:
        """Get the status and metadata of a job."""
        item = self._jobs.get(job_id)
        return item.record if item else None

    def list_jobs(self, status: JobStatus | None = None, limit: int = 50) -> list[JobRecord]:
        """List registered jobs with optional status filter."""
        records = [item.record for item in self._jobs.values()]
        if status:
            records = [r for r in records if r.status == status]
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[:limit]

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a queued or actively executing job."""
        item = self._jobs.get(job_id)
        if not item:
            return False

        if item.record.status == JobStatus.QUEUED:
            item.record.status = JobStatus.CANCELLED
            item.record.completed_at = time.time()
            self._total_cancelled += 1
            return True

        if item.record.status == JobStatus.RUNNING:
            task = self._running_tasks.get(job_id)
            if task and not task.done():
                task.cancel()
                item.record.status = JobStatus.CANCELLED
                item.record.completed_at = time.time()
                self._total_cancelled += 1
                return True

        return False

    async def _execute_job(self, item: _JobItem) -> None:
        """Execute a single job item with timeout, retry, and metric tracking."""
        record = item.record
        record.started_at = time.time()
        record.status = JobStatus.RUNNING

        while True:
            t0 = time.perf_counter()
            try:
                task = asyncio.create_task(item.fn(*item.args, **item.kwargs))
                self._running_tasks[record.id] = task

                result = await asyncio.wait_for(task, timeout=record.timeout_seconds)
                exec_ms = int((time.perf_counter() - t0) * 1000)

                record.status = JobStatus.COMPLETED
                record.result = result
                record.completed_at = time.time()
                record.execution_ms = exec_ms
                self._total_completed += 1
                self._total_execution_ms += exec_ms
                logger.debug("Job '%s' (%s) completed in %d ms", record.name, record.id, exec_ms)
                return

            except asyncio.TimeoutError:
                exec_ms = int((time.perf_counter() - t0) * 1000)
                record.status = JobStatus.TIMEOUT
                record.error = f"Job timed out after {record.timeout_seconds}s"
                record.completed_at = time.time()
                record.execution_ms = exec_ms
                self._total_timeouts += 1
                logger.warning("Job '%s' (%s) timed out", record.name, record.id)
                return

            except asyncio.CancelledError:
                exec_ms = int((time.perf_counter() - t0) * 1000)
                record.status = JobStatus.CANCELLED
                record.completed_at = time.time()
                record.execution_ms = exec_ms
                return

            except Exception as exc:
                exec_ms = int((time.perf_counter() - t0) * 1000)
                if record.retry_count < record.max_retries:
                    record.retry_count += 1
                    logger.info(
                        "Retrying job '%s' (%s) (attempt %d/%d) after error: %s",
                        record.name,
                        record.id,
                        record.retry_count,
                        record.max_retries,
                        exc,
                    )
                    await asyncio.sleep(0.1 * (2 ** (record.retry_count - 1)))
                    continue

                record.status = JobStatus.FAILED
                record.error = str(exc)
                record.completed_at = time.time()
                record.execution_ms = exec_ms
                self._total_failed += 1
                logger.error("Job '%s' (%s) failed: %s", record.name, record.id, exc)
                return

            finally:
                self._running_tasks.pop(record.id, None)

    async def _worker_loop(self) -> None:
        """Worker loop continuously pulling prioritized jobs."""
        while self._running:
            try:
                _, _, job_id = await self._queue.get()
            except asyncio.CancelledError:
                break

            try:
                item = self._jobs.get(job_id)
                if item and item.record.status == JobStatus.QUEUED:
                    await self._execute_job(item)
            finally:
                self._queue.task_done()

    async def start(self) -> None:
        """Start the background worker pool."""
        if not self._running:
            self._running = True
            for i in range(self.max_workers):
                task = asyncio.create_task(self._worker_loop(), name=f"job-worker-{i}")
                self._worker_tasks.append(task)
            logger.info("AsyncJobDispatcher started with %d workers", self.max_workers)

    async def stop(self, wait: bool = True) -> None:
        """Stop worker pool and cancel any pending workers."""
        if self._running:
            self._running = False
            for task in self._worker_tasks:
                task.cancel()
            if wait and self._worker_tasks:
                await asyncio.gather(*self._worker_tasks, return_exceptions=True)
            self._worker_tasks.clear()
            self._running_tasks.clear()
            logger.info("AsyncJobDispatcher stopped")

    async def wait_for_job(
        self,
        job_id: str,
        poll_interval: float = 0.05,
        timeout: float | None = None,
    ) -> JobRecord:
        """Wait until a submitted job reaches a terminal state."""
        start_time = time.time()
        while True:
            record = self.get_job(job_id)
            if not record:
                raise KeyError(f"Job {job_id} not found")
            if record.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.TIMEOUT, JobStatus.CANCELLED):
                return record
            if timeout and (time.time() - start_time) > timeout:
                raise TimeoutError(f"Timed out waiting for job {job_id}")
            await asyncio.sleep(poll_interval)

    def get_metrics(self) -> dict[str, Any]:
        """Return operational metrics for dispatcher throughput and error rates."""
        avg_latency = (
            (self._total_execution_ms / self._total_completed)
            if self._total_completed > 0
            else 0.0
        )
        return {
            "queue_depth": self._queue.qsize(),
            "active_workers": len(self._running_tasks),
            "max_workers": self.max_workers,
            "completed": self._total_completed,
            "failed": self._total_failed,
            "timeouts": self._total_timeouts,
            "cancelled": self._total_cancelled,
            "avg_latency_ms": round(avg_latency, 2),
        }
