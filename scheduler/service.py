"""FlowCore Scheduler — periodic task scheduling.

Wraps APScheduler (AsyncIOScheduler) to schedule recurring tasks.
Lightweight enough for Termux; only one scheduler instance per process.
"""
from __future__ import annotations

from typing import Any, Callable, Coroutine

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger


class SchedulerService:
    """Simple scheduler service wrapping APScheduler.

    Usage::

        scheduler = SchedulerService()
        await scheduler.start()
        scheduler.add_interval_task(name="heartbeat", interval=60, func=heartbeat)
        await scheduler.stop()
    """

    def __init__(self, timezone: str = "America/Sao_Paulo") -> None:
        self._scheduler = AsyncIOScheduler(timezone=timezone)
        self._running = False
        self._jobs: dict[str, Any] = {}

    async def start(self) -> None:
        self._scheduler.start()
        self._running = True
        logger.info("Scheduler started (timezone={})", self._scheduler.timezone)

    async def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
        self._running = False
        logger.info("Scheduler stopped")

    def add_interval_task(
        self,
        name: str,
        interval: int,
        func: Callable[..., Coroutine[Any, Any, Any]],
        args: tuple = (),
        kwargs: dict | None = None,
    ) -> str:
        """Add a task that runs every *interval* seconds."""
        job = self._scheduler.add_job(
            func,
            trigger=IntervalTrigger(seconds=interval),
            id=name,
            args=args,
            kwargs=kwargs or {},
            replace_existing=True,
        )
        self._jobs[name] = job
        logger.info("Scheduled '{}' every {}s", name, interval)
        return job.id

    def remove_task(self, name: str) -> bool:
        """Remove a scheduled task by name."""
        try:
            self._scheduler.remove_job(name)
            self._jobs.pop(name, None)
            return True
        except Exception:
            return False

    def list_tasks(self) -> list[dict[str, Any]]:
        """Return a list of all scheduled jobs."""
        return [
            {"id": job.id, "name": job.id, "next_run": str(job.next_run_time)}
            for job in self._scheduler.get_jobs()
        ]

    @property
    def is_running(self) -> bool:
        return self._running
