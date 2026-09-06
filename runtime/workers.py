"""Persistent background workers for FlowCore event loop, orchestration, and periodic monitoring."""

from __future__ import annotations

import asyncio
import time
from typing import NoReturn

from runtime.events.bus import get_event_bus
from agents.orchestrator import get_orchestrator
from runtime.events.schemas import Event, EventPriority


class EventWorker:
    """Worker that continuously consumes pending events and triggers Orchestrator."""

    def __init__(self, poll_interval: float = 2.0) -> None:
        self.poll_interval = poll_interval
        self.orchestrator = get_orchestrator()

    async def run_loop(self) -> None:
        while True:
            try:
                await self.orchestrator.run()
            except Exception as e:
                print(f"[EventWorker Error] {e}")
            await asyncio.sleep(self.poll_interval)


class SchedulerWorker:
    """Worker that periodically generates system events (e.g. morning briefing, portfolio scans)."""

    def __init__(self, scan_interval: float = 300.0) -> None:
        self.scan_interval = scan_interval

    async def run_loop(self) -> None:
        event_bus = get_event_bus()
        while True:
            try:
                # Periodic scan event
                evt = Event(
                    type="PORTFOLIO_OUT_OF_PROFILE",
                    source="scheduler_worker",
                    entity="cli_001",
                    payload={"reason": "Periodic background scan"},
                    priority=EventPriority.MEDIUM,
                )
                event_bus.publish(evt)
            except Exception as e:
                print(f"[SchedulerWorker Error] {e}")
            await asyncio.sleep(self.scan_interval)


async def start_all_workers() -> None:
    event_worker = EventWorker(poll_interval=1.0)
    scheduler_worker = SchedulerWorker(scan_interval=60.0)

    asyncio.create_task(event_worker.run_loop())
    asyncio.create_task(scheduler_worker.run_loop())
