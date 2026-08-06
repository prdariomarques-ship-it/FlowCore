"""Tests for runtime.outlook — Outlook-specific logic (Sprint 17, Milestone 2).

As of Milestone 3, auth/token/generic-Graph-request plumbing lives in
runtime.microsoft_graph (see tests/test_microsoft_graph.py) — this file
only tests what's still specific to Outlook: message listing/search/
formatting. graph_get is patched directly rather than the underlying
requests/msal mocks, since that's the actual boundary this module owns.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# msal/requests are requirements-api.txt (optional) — skip gracefully on a
# core-only install instead of failing (same pattern as test_api.py's
# fastapi/httpx importorskip). runtime.outlook imports runtime.microsoft_graph,
# which imports both.
msal = pytest.importorskip("msal")
requests = pytest.importorskip("requests")


class TestBackwardCompatibleNames:
    """runtime/outlook.py's public API must stay identical after the
    Milestone 3 extraction — nothing that already imports from it should
    need to change."""

    def test_error_classes_importable(self):
        from runtime.outlook import OutlookAuthRequiredError, OutlookError, OutlookNotConfiguredError

        assert issubclass(OutlookNotConfiguredError, OutlookError)
        assert issubclass(OutlookAuthRequiredError, OutlookError)

    def test_auth_functions_importable(self):
        from runtime.outlook import complete_device_flow, is_authenticated, start_device_flow

        assert callable(start_device_flow)
        assert callable(complete_device_flow)
        assert callable(is_authenticated)

    def test_error_classes_are_shared_with_calendar(self):
        # Same underlying classes as runtime.microsoft_graph — a caller
        # catching OutlookError also catches what Calendar raises, and
        # vice versa, since they're the same auth/Graph layer.
        from runtime.calendar import CalendarError
        from runtime.outlook import OutlookError

        assert OutlookError is CalendarError


class TestMessageOperations:
    def test_list_messages_parses_response(self):
        import runtime.outlook as mod

        payload = {
            "value": [
                {
                    "subject": "Hello",
                    "from": {"emailAddress": {"name": "Alice", "address": "alice@example.com"}},
                    "receivedDateTime": "2026-08-05T10:00:00Z",
                    "isRead": False,
                }
            ]
        }
        with patch.object(mod, "graph_get", return_value=payload) as m:
            result = mod.list_messages(limit=5)
        assert result == [{"subject": "Hello", "from": "Alice", "received": "2026-08-05T10:00:00Z", "is_read": False}]
        args, kwargs = m.call_args
        assert args[1]["$top"] == "5"

    def test_get_unread_count(self):
        import runtime.outlook as mod

        with patch.object(mod, "graph_get", return_value={"unreadItemCount": 7}):
            assert mod.get_unread_count() == 7

    def test_search_messages(self):
        import runtime.outlook as mod

        payload = {
            "value": [
                {
                    "subject": "Invoice",
                    "from": {"emailAddress": {"address": "billing@example.com"}},
                    "receivedDateTime": "2026-08-01T00:00:00Z",
                    "isRead": True,
                }
            ]
        }
        with patch.object(mod, "graph_get", return_value=payload) as m:
            result = mod.search_messages("invoice", limit=3)
        assert result[0]["from"] == "billing@example.com"  # falls back to address when no name
        args, kwargs = m.call_args
        assert args[1]["$search"] == '"invoice"'

    def test_list_messages_empty_result(self):
        import runtime.outlook as mod

        with patch.object(mod, "graph_get", return_value={"value": []}):
            assert mod.list_messages() == []

    def test_graph_get_error_propagates(self):
        import runtime.outlook as mod

        with patch.object(mod, "graph_get", side_effect=mod.OutlookError("Graph API error 403: Forbidden")):
            with pytest.raises(mod.OutlookError, match="403"):
                mod.list_messages()
