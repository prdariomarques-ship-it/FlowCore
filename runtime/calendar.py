"""FlowCore — Microsoft Calendar integration (Sprint 17, Milestone 3).

Shares the exact same authenticated session as runtime/outlook.py — both
import their auth/token/Graph-request plumbing from
runtime/microsoft_graph.py. No second OAuth implementation, no second
Graph client.

Read operations use Graph's /me/calendarView (not /me/events with a date
filter) for date-range queries — calendarView correctly expands recurring
event instances into the range; /me/events does not.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from runtime.microsoft_graph import (
    MicrosoftGraphAuthRequiredError as CalendarAuthRequiredError,
    MicrosoftGraphError as CalendarError,
    MicrosoftGraphNotConfiguredError as CalendarNotConfiguredError,
    graph_get,
)

__all__ = [
    "CalendarError",
    "CalendarNotConfiguredError",
    "CalendarAuthRequiredError",
    "list_today",
    "list_tomorrow",
    "list_week",
    "get_next",
    "search_events",
]


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _day_range(days_from_today: int) -> tuple[str, str]:
    start = (datetime.now(timezone.utc) + timedelta(days=days_from_today)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return _iso(start), _iso(start + timedelta(days=1))


def _calendar_view(start: str, end: str, top: int = 50) -> list[dict[str, Any]]:
    data = graph_get(
        "/me/calendarView",
        {"startDateTime": start, "endDateTime": end, "$orderby": "start/dateTime", "$top": str(top)},
    )
    return [_format_event(e) for e in data.get("value", [])]


def list_today() -> list[dict[str, Any]]:
    start, end = _day_range(0)
    return _calendar_view(start, end)


def list_tomorrow() -> list[dict[str, Any]]:
    start, end = _day_range(1)
    return _calendar_view(start, end)


def list_week() -> list[dict[str, Any]]:
    start = _iso(datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0))
    end = _iso(datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=7))
    return _calendar_view(start, end)


def get_next() -> dict[str, Any] | None:
    """The next upcoming event within the next 30 days, or None."""
    now = datetime.now(timezone.utc)
    events = _calendar_view(_iso(now), _iso(now + timedelta(days=30)), top=1)
    return events[0] if events else None


def search_events(query: str, limit: int = 10) -> list[dict[str, Any]]:
    data = graph_get("/me/events", {"$search": f'"{query}"', "$top": str(limit)})
    return [_format_event(e) for e in data.get("value", [])]


def _format_event(e: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": e.get("id", ""),
        "subject": e.get("subject", ""),
        "start": (e.get("start") or {}).get("dateTime", ""),
        "end": (e.get("end") or {}).get("dateTime", ""),
        "timezone": (e.get("start") or {}).get("timeZone", ""),
        "location": (e.get("location") or {}).get("displayName", ""),
        "organizer": ((e.get("organizer") or {}).get("emailAddress") or {}).get("name", ""),
    }
