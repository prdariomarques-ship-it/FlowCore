"""Observer scheduler — runs registered Observers, on demand or on a loop.

run_once() powers on-demand inspection (API/CLI/MCP). run_forever() is a
standalone, independently runnable loop (e.g. `flowcore.py observer
watch`) — not auto-started inside the FastAPI process or FlowCoreDaemon
in this phase, since nothing downstream (Alert Engine, future sprint)
consumes always-on collection yet.
"""

from __future__ import annotations

import asyncio

from loguru import logger

from runtime.observers.base import Observer, ObserverError
from runtime.observers.event import MarketEvent
from runtime.observers.registry import ObserverRegistry, registry as _default_registry


class ObserverScheduler:
    def __init__(self, observer_registry: ObserverRegistry) -> None:
        self._registry = observer_registry

    async def run_once(self) -> list[MarketEvent]:
        observers = self._registry.all()
        results = await asyncio.gather(*(asyncio.to_thread(self._observe_safely, obs) for obs in observers))
        events: list[MarketEvent] = []
        for result in results:
            events.extend(result)
        return events

    def _observe_safely(self, observer: Observer) -> list[MarketEvent]:
        try:
            return observer.observe()
        except ObserverError as e:
            logger.warning(f"Observer {observer.source!r} failed this cycle: {e}")
            return []

    async def run_forever(self, interval_seconds: float) -> None:
        while True:
            events = await self.run_once()
            logger.info(f"Observer cycle: {len(events)} event(s)")
            await asyncio.sleep(interval_seconds)


scheduler = ObserverScheduler(_default_registry)
