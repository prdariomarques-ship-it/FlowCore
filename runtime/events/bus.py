"""Persistent async Event Bus for FlowCore Agentic Platform."""

from __future__ import annotations

import json
import asyncio
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from runtime.events.schemas import Event, EventPriority, EventStatus

STORAGE_DIR = Path(__file__).resolve().parent.parent.parent / "storage"
EVENTS_FILE = STORAGE_DIR / "events.json"


class EventBus:
    def __init__(self, storage_file: Path = EVENTS_FILE) -> None:
        self.storage_file = storage_file
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        self._subscribers: Dict[str, List[Callable[[Event], Any]]] = {}
        if not self.storage_file.exists():
            self._save([])

    def _load(self) -> List[Dict[str, Any]]:
        try:
            with open(self.storage_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save(self, events: List[Dict[str, Any]]) -> None:
        with open(self.storage_file, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2, ensure_ascii=False)

    def subscribe(self, event_type: str, handler: Callable[[Event], Any]) -> None:
        """Subscribe a handler to a specific event type or '*' for all events."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def publish(self, event: Event) -> Dict[str, Any]:
        """Publish an event to persistent storage and notify synchronously/asynchronously."""
        events_data = self._load()
        events_data.append(event.to_dict())
        self._save(events_data)

        # Notify handlers
        handlers = self._subscribers.get(event.type, []) + self._subscribers.get("*", [])
        for handler in handlers:
            try:
                res = handler(event)
                if asyncio.iscoroutine(res):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(res)
                    except RuntimeError:
                        asyncio.run(res)
            except Exception as e:
                print(f"[EventBus Error] Handler failed for {event.id}: {e}")

        return event.to_dict()

    def get_pending_events(self) -> List[Event]:
        raw_events = self._load()
        pending = [Event.from_dict(e) for e in raw_events if e.get("status") == EventStatus.PENDING.value]
        # Sort by priority
        priority_order = {
            EventPriority.CRITICAL.value: 0,
            EventPriority.HIGH.value: 1,
            EventPriority.MEDIUM.value: 2,
            EventPriority.LOW.value: 3,
        }
        pending.sort(key=lambda x: priority_order.get(x.priority.value, 4))
        return pending

    def update_event_status(self, event_id: str, status: EventStatus, metadata: Optional[Dict[str, Any]] = None) -> None:
        events_data = self._load()
        for e in events_data:
            if e.get("id") == event_id:
                e["status"] = status.value
                if metadata:
                    e.setdefault("metadata", {}).update(metadata)
                break
        self._save(events_data)

    def list_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        raw = self._load()
        return raw[-limit:]


_bus_instance = EventBus()

def get_event_bus() -> EventBus:
    return _bus_instance
