"""FlowCore — Outlook integration (Microsoft Graph, read-only).

Sprint 17, Milestone 2. Mail-specific only — auth, token cache, and the
generic Graph HTTP helpers live in runtime/microsoft_graph.py (extracted
in Milestone 3 so Calendar could reuse them without a second OAuth
implementation). The names below are unchanged from Milestone 2: every
existing caller (service.py, api/router.py, flowcore.py, mcp_server.py,
tests/test_outlook.py) keeps working without modification.

Read-only: Mail.Read scope only. No sending, no folder management.
"""

from __future__ import annotations

from typing import Any

from runtime.microsoft_graph import (
    MicrosoftGraphAuthRequiredError as OutlookAuthRequiredError,
    MicrosoftGraphError as OutlookError,
    MicrosoftGraphNotConfiguredError as OutlookNotConfiguredError,
    complete_device_flow,
    graph_get,
    is_authenticated,
    start_device_flow,
)

__all__ = [
    "OutlookError",
    "OutlookNotConfiguredError",
    "OutlookAuthRequiredError",
    "start_device_flow",
    "complete_device_flow",
    "is_authenticated",
    "list_messages",
    "get_unread_count",
    "search_messages",
]


def list_messages(limit: int = 10) -> list[dict[str, Any]]:
    data = graph_get(
        "/me/messages",
        {
            "$top": str(limit),
            "$orderby": "receivedDateTime desc",
            "$select": "subject,from,receivedDateTime,isRead",
        },
    )
    return [_format_message(m) for m in data.get("value", [])]


def get_unread_count() -> int:
    data = graph_get("/me/mailFolders/inbox", {"$select": "unreadItemCount"})
    return data.get("unreadItemCount", 0)


def search_messages(query: str, limit: int = 10) -> list[dict[str, Any]]:
    data = graph_get("/me/messages", {"$search": f'"{query}"', "$top": str(limit)})
    return [_format_message(m) for m in data.get("value", [])]


def _format_message(m: dict[str, Any]) -> dict[str, Any]:
    sender = (m.get("from") or {}).get("emailAddress", {})
    return {
        "subject": m.get("subject", ""),
        "from": sender.get("name") or sender.get("address", ""),
        "received": m.get("receivedDateTime", ""),
        "is_read": m.get("isRead", False),
    }
