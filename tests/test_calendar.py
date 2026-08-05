"""Tests for runtime.calendar — Calendar read operations (Sprint 17, Milestone 3).

Shares auth with Outlook (runtime.microsoft_graph — see
tests/test_microsoft_graph.py for that layer's own coverage). graph_get is
patched directly, mirroring tests/test_outlook.py's approach — this file
tests date-range computation, event formatting, and Graph query
construction, not the shared HTTP/auth mechanics.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

msal = pytest.importorskip("msal")
requests = pytest.importorskip("requests")


class TestBackwardCompatibleNames:
    def test_error_classes_shared_with_outlook(self):
        from runtime.calendar import CalendarAuthRequiredError, CalendarError, CalendarNotConfiguredError
        from runtime.outlook import OutlookAuthRequiredError, OutlookError, OutlookNotConfiguredError

        assert CalendarError is OutlookError
        assert CalendarNotConfiguredError is OutlookNotConfiguredError
        assert CalendarAuthRequiredError is OutlookAuthRequiredError


class TestDateRanges:
    def test_today_range_is_midnight_to_midnight(self):
        import runtime.calendar as mod

        start, end = mod._day_range(0)
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        assert start_dt.hour == 0 and start_dt.minute == 0
        assert (end_dt - start_dt).total_seconds() == 86400

    def test_tomorrow_range_is_one_day_after_today(self):
        import runtime.calendar as mod

        today_start, _ = mod._day_range(0)
        tomorrow_start, _ = mod._day_range(1)
        delta = datetime.fromisoformat(tomorrow_start) - datetime.fromisoformat(today_start)
        assert delta.days == 1


class TestReadOperations:
    def test_list_today_queries_calendar_view(self):
        import runtime.calendar as mod

        with patch.object(mod, "graph_get", return_value={"value": []}) as m:
            result = mod.list_today()
        assert result == []
        args, kwargs = m.call_args
        assert args[0] == "/me/calendarView"
        assert "startDateTime" in args[1]
        assert "endDateTime" in args[1]

    def test_list_today_formats_events(self):
        import runtime.calendar as mod

        payload = {
            "value": [
                {
                    "id": "AAMk123",
                    "subject": "Standup",
                    "start": {"dateTime": "2026-08-05T09:00:00", "timeZone": "UTC"},
                    "end": {"dateTime": "2026-08-05T09:30:00", "timeZone": "UTC"},
                    "location": {"displayName": "Room 1"},
                    "organizer": {"emailAddress": {"name": "Bob", "address": "bob@example.com"}},
                }
            ]
        }
        with patch.object(mod, "graph_get", return_value=payload):
            result = mod.list_today()
        assert result == [
            {
                "id": "AAMk123",
                "subject": "Standup",
                "start": "2026-08-05T09:00:00",
                "end": "2026-08-05T09:30:00",
                "timezone": "UTC",
                "location": "Room 1",
                "organizer": "Bob",
            }
        ]

    def test_get_next_returns_first_event(self):
        import runtime.calendar as mod

        payload = {
            "value": [
                {
                    "id": "e1",
                    "subject": "1:1",
                    "start": {"dateTime": "2026-08-06T10:00:00", "timeZone": "UTC"},
                    "end": {"dateTime": "2026-08-06T10:30:00", "timeZone": "UTC"},
                }
            ]
        }
        with patch.object(mod, "graph_get", return_value=payload) as m:
            result = mod.get_next()
        assert result["subject"] == "1:1"
        args, kwargs = m.call_args
        assert args[1]["$top"] == "1"

    def test_get_next_returns_none_when_no_events(self):
        import runtime.calendar as mod

        with patch.object(mod, "graph_get", return_value={"value": []}):
            assert mod.get_next() is None

    def test_search_events(self):
        import runtime.calendar as mod

        payload = {
            "value": [
                {
                    "id": "e2",
                    "subject": "Budget review",
                    "start": {"dateTime": "2026-08-10T14:00:00", "timeZone": "UTC"},
                    "end": {"dateTime": "2026-08-10T15:00:00", "timeZone": "UTC"},
                }
            ]
        }
        with patch.object(mod, "graph_get", return_value=payload) as m:
            result = mod.search_events("budget", limit=5)
        assert result[0]["subject"] == "Budget review"
        args, kwargs = m.call_args
        assert args[0] == "/me/events"
        assert args[1]["$search"] == '"budget"'
        assert args[1]["$top"] == "5"

    def test_format_event_missing_fields_default_gracefully(self):
        import runtime.calendar as mod

        result = mod._format_event({})
        assert result == {
            "id": "",
            "subject": "",
            "start": "",
            "end": "",
            "timezone": "",
            "location": "",
            "organizer": "",
        }
