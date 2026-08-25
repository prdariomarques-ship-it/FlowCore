"""Observer scheduler — runs registered Observers, on demand or on a loop.

run_once()/run_source() power on-demand inspection (API/CLI/MCP).
run_forever() is a standalone, independently runnable loop (e.g.
`flowcore.py observer watch`) — not auto-started inside the FastAPI
process or FlowCoreDaemon in this phase, since nothing downstream (Alert
Engine, future sprint) consumes always-on collection yet.

Sprint 19: every MarketEvent produced by either method is persisted via
an injected EventRepository, when one is present — doesn't matter if the
call came from the CLI, API, MCP, or the watch loop. This is what gives
the Macro Score Engine real history to compute against.
"""

from __future__ import annotations

import asyncio

from loguru import logger

from runtime.observers.base import Observer, ObserverError
from runtime.observers.event import MarketEvent
from runtime.observers.registry import ObserverRegistry, registry as _default_registry


class ObserverScheduler:
    def __init__(self, observer_registry: ObserverRegistry, event_repo=None) -> None:
        self._registry = observer_registry
        self._event_repo = event_repo

    async def run_once(self) -> list[MarketEvent]:
        observers = self._registry.all()
        results = await asyncio.gather(*(asyncio.to_thread(self._observe_safely, obs) for obs in observers))
        events: list[MarketEvent] = []
        for result in results:
            events.extend(result)
        await self._persist(events)
        return events

    async def run_source(self, source: str) -> list[MarketEvent]:
        """Run a single registered observer by name and persist its event(s).
        Raises ObserverError (via registry.get) for an unknown source."""
        observer = self._registry.get(source)
        events = await asyncio.to_thread(observer.observe)
        await self._persist(events)
        return events

    async def _persist(self, events: list[MarketEvent]) -> None:
        if self._event_repo is None or not events:
            return
        try:
            await asyncio.gather(*(self._event_repo.insert_event(e.to_dict()) for e in events))
        except Exception as e:
            # A storage hiccup shouldn't break a live status check — log and
            # move on, same "one failure doesn't sink the batch" philosophy
            # as _observe_safely below.
            logger.warning(f"Failed to persist {len(events)} event(s): {e}")

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


def _default_event_repo():
    from storage import EventRepository

    return EventRepository()


scheduler = ObserverScheduler(_default_registry, event_repo=_default_event_repo())
