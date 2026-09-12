"""FlowCore Executor — task execution engine.

Handles:
- Task queue management
- Execution with retry logic
- Status tracking
- Result storage

Thread-safe and designed for low-resource Termux environments.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from enum import Enum
from typing import Any, Callable, Coroutine

from loguru import logger


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task:
    """A unit of work to be executed."""

    def __init__(
        self,
        name: str,
        handler: Callable[..., Coroutine[Any, Any, Any]],
        args: tuple = (),
        kwargs: dict | None = None,
        retries: int = 3,
        retry_delay: float = 5.0,
        timeout: float = 30.0,
    ) -> None:
        self.id = uuid.uuid4().hex
        self.name = name
        self.handler = handler
        self.args = args
        self.kwargs = kwargs or {}
        self.retries = retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.status = TaskStatus.PENDING
        self.result: Any = None
        self.error: str | None = None
        self.created_at = time.time()
        self.started_at: float | None = None
        self.finished_at: float | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class ExecutorEngine:
    """Async task executor with queue, retry, and timeout.

    Usage::

        engine = ExecutorEngine(max_concurrent=2)
        await engine.start()
        task = Task(name="my_task", handler=my_coro)
        task = await engine.submit(task)
        await engine.stop()
    """

    def __init__(self, max_concurrent: int = 2, max_queue: int = 100) -> None:
        self._max_concurrent = max_concurrent
        self._max_queue = max_queue
        self._queue: asyncio.Queue[Task] = asyncio.Queue(maxsize=max_queue)
        self._workers: list[asyncio.Task] = []
        self._tasks: dict[str, Task] = {}
        self._running = False
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def start(self) -> None:
        self._running = True
        logger.info("Executor started (workers={}, max_queue={})", self._max_concurrent, self._max_queue)

    async def stop(self) -> None:
        self._running = False
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("Executor stopped")

    async def submit(self, task: Task) -> Task:
        """Submit a task for execution."""
        if self._queue.full():
            task.status = TaskStatus.FAILED
            task.error = "Queue full"
            return task

        self._tasks[task.id] = task
        await self._queue.put(task)

        # Start workers lazily
        if len(self._workers) < self._max_concurrent:
            worker = asyncio.create_task(self._worker_loop())
            self._workers.append(worker)

        return task

    async def _worker_loop(self) -> None:
        """Worker coroutine that processes tasks from the queue."""
        while self._running:
            try:
                task = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                await asyncio.sleep(0.1)
                continue

            await self._execute_task(task)
            self._queue.task_done()

    async def _execute_task(self, task: Task) -> None:
        """Execute a single task with retry and timeout."""
        async with self._semaphore:
            for attempt in range(task.retries + 1):
                task.status = TaskStatus.RUNNING
                task.started_at = time.time()
                try:
                    result = await asyncio.wait_for(
                        task.handler(*task.args, **task.kwargs),
                        timeout=task.timeout,
                    )
                    task.result = result
                    task.status = TaskStatus.COMPLETED
                    task.finished_at = time.time()
                    logger.info("Task {} completed: {}", task.name, task.id)
                    return
                except asyncio.TimeoutError:
                    task.error = f"Timeout after {task.timeout}s"
                except Exception as exc:
                    task.error = str(exc)
                    logger.warning("Task {} attempt {} failed: {}", task.name, attempt + 1, exc)

                if attempt < task.retries:
                    logger.info("Task {} retrying in {}s...", task.name, task.retry_delay)
                    await asyncio.sleep(task.retry_delay)

            task.status = TaskStatus.FAILED
            task.finished_at = time.time()
            logger.error("Task {} permanently failed: {}", task.name, task.error)

    def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[Task]:
        return list(self._tasks.values())
