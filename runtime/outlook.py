"""FlowCore — Outlook integration (Microsoft Graph, read-only).

Sprint 17, Milestone 2. Device Code Flow only — no redirect URI, no local
web server: FlowCore prints a code, the user authorizes once at
microsoft.com/devicelogin, and the token is cached locally
(~/.flowcore/outlook_token_cache.json) and refreshes itself silently after
that (same UX as `gh auth login`).

Uses Microsoft's own `msal` library rather than hand-rolling OAuth2 token
refresh — unlike runtime/ollama.py or runtime/telegram.py-style bearer-token
APIs, getting refresh-token handling wrong by hand is a real security
footgun, not just extra code.

Read-only: Mail.Read scope only. No sending, no folder management.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import msal
import requests

SCOPES = ["Mail.Read"]
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

_CACHE_FILE = Path.home() / ".flowcore" / "outlook_token_cache.json"


class OutlookError(RuntimeError):
    """Base class for all Outlook-related errors raised by FlowCore."""


class OutlookNotConfiguredError(OutlookError):
    """OUTLOOK_CLIENT_ID / OUTLOOK_TENANT_ID not set."""


class OutlookAuthRequiredError(OutlookError):
    """No valid cached token — the user needs to complete the device code flow."""


def _require_config() -> tuple[str, str]:
    client_id = os.getenv("OUTLOOK_CLIENT_ID")
    tenant_id = os.getenv("OUTLOOK_TENANT_ID", "common")
    if not client_id:
        raise OutlookNotConfiguredError(
            "OUTLOOK_CLIENT_ID not set. Register an app at https://portal.azure.com "
            "(public client, Device Code Flow, Mail.Read permission) and add it to .env."
        )
    return client_id, tenant_id


def _load_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if _CACHE_FILE.exists():
        cache.deserialize(_CACHE_FILE.read_text(encoding="utf-8"))
    return cache


def _save_cache(cache: msal.SerializableTokenCache) -> None:
    if cache.has_state_changed:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(cache.serialize(), encoding="utf-8")


def _app(cache: msal.SerializableTokenCache | None = None) -> msal.PublicClientApplication:
    client_id, tenant_id = _require_config()
    return msal.PublicClientApplication(
        client_id=client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        token_cache=cache if cache is not None else _load_cache(),
    )


def start_device_flow() -> dict[str, Any]:
    """Begin the device code flow. Does not block.

    Returns the flow dict (must be passed to complete_device_flow) plus the
    user-facing fields: user_code, verification_uri, expires_in, message.
    """
    app = _app()
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise OutlookError(flow.get("error_description", "Failed to start device flow"))
    return flow


def complete_device_flow(flow: dict[str, Any]) -> None:
    """Block, polling until the user authorizes (or the flow expires/fails).

    Saves the token cache on success. Raises OutlookError on failure/expiry.
    """
    cache = _load_cache()
    app = _app(cache)
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise OutlookError(result.get("error_description", "Device flow did not complete"))
    _save_cache(cache)


def is_authenticated() -> bool:
    """True if a valid (or silently refreshable) cached token exists."""
    try:
        cache = _load_cache()
        app = _app(cache)
    except OutlookNotConfiguredError:
        return False
    accounts = app.get_accounts()
    if not accounts:
        return False
    result = app.acquire_token_silent(SCOPES, account=accounts[0])
    _save_cache(cache)
    return result is not None and "access_token" in result


def _access_token() -> str:
    cache = _load_cache()
    app = _app(cache)
    accounts = app.get_accounts()
    if not accounts:
        raise OutlookAuthRequiredError("Not authenticated yet — run the device code flow first.")
    result = app.acquire_token_silent(SCOPES, account=accounts[0])
    _save_cache(cache)
    if not result or "access_token" not in result:
        raise OutlookAuthRequiredError("Cached token expired or revoked — re-run the device code flow.")
    return result["access_token"]


def _graph_get(path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    token = _access_token()
    try:
        r = requests.get(
            f"{GRAPH_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params or {},
            timeout=10,
        )
    except requests.RequestException as e:
        raise OutlookError(f"Graph API request failed: {e}") from e
    if r.status_code != 200:
        raise OutlookError(f"Graph API error {r.status_code}: {r.text[:300]}")
    return r.json()


def list_messages(limit: int = 10) -> list[dict[str, Any]]:
    data = _graph_get(
        "/me/messages",
        {
            "$top": str(limit),
            "$orderby": "receivedDateTime desc",
            "$select": "subject,from,receivedDateTime,isRead",
        },
    )
    return [_format_message(m) for m in data.get("value", [])]


def get_unread_count() -> int:
    data = _graph_get("/me/mailFolders/inbox", {"$select": "unreadItemCount"})
    return data.get("unreadItemCount", 0)


def search_messages(query: str, limit: int = 10) -> list[dict[str, Any]]:
    data = _graph_get("/me/messages", {"$search": f'"{query}"', "$top": str(limit)})
    return [_format_message(m) for m in data.get("value", [])]


def _format_message(m: dict[str, Any]) -> dict[str, Any]:
    sender = (m.get("from") or {}).get("emailAddress", {})
    return {
        "subject": m.get("subject", ""),
        "from": sender.get("name") or sender.get("address", ""),
        "received": m.get("receivedDateTime", ""),
        "is_read": m.get("isRead", False),
    }
