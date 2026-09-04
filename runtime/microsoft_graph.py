"""FlowCore — shared Microsoft Graph provider (auth, token cache, HTTP).

Sprint 17, Milestone 3. Extracted from runtime/outlook.py so Calendar
(runtime/calendar.py) can reuse the exact same authenticated session
instead of a second OAuth implementation — the user's explicit rule for
this milestone ("no second authentication flow", "do not create another
Graph client"). runtime/outlook.py's public API is unchanged: it imports
and re-exports the names it needs from here under their original names
(OutlookError, start_device_flow, ...), so nothing that already calls
into it needed to change.

Device Code Flow only — no redirect URI, no local web server: FlowCore
prints a code, the user authorizes once at microsoft.com/devicelogin, and
the token is cached locally (~/.flowcore/outlook_token_cache.json — one
file, one session, shared by mail and calendar) and refreshes itself
silently after that (same UX as `gh auth login`).

Uses Microsoft's own `msal` library rather than hand-rolling OAuth2 token
refresh — getting refresh-token handling wrong by hand is a real security
footgun, not just extra code.

SCOPES covers every FlowCore Graph integration that exists so far
(Mail.Read for Outlook, Calendar.ReadWrite for Calendar) — requested
together in one flow. Adding a future Graph integration means adding its
scope here, not starting a new auth flow.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import msal
import requests

SCOPES = ["Mail.Read", "Calendar.ReadWrite"]
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

_CACHE_FILE = Path.home() / ".flowcore" / "outlook_token_cache.json"


class MicrosoftGraphError(RuntimeError):
    """Base class for all Microsoft Graph errors raised by FlowCore."""


class MicrosoftGraphNotConfiguredError(MicrosoftGraphError):
    """OUTLOOK_CLIENT_ID / OUTLOOK_TENANT_ID not set."""


class MicrosoftGraphAuthRequiredError(MicrosoftGraphError):
    """No valid cached token — the user needs to complete the device code flow."""


def _require_config() -> tuple[str, str]:
    client_id = os.getenv("OUTLOOK_CLIENT_ID")
    tenant_id = os.getenv("OUTLOOK_TENANT_ID", "common")
    if not client_id:
        raise MicrosoftGraphNotConfiguredError(
            "OUTLOOK_CLIENT_ID not set. Register an app at https://portal.azure.com "
            "(public client, Device Code Flow, Mail.Read + Calendar.ReadWrite permissions) "
            "and add it to .env."
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
        raise MicrosoftGraphError(flow.get("error_description", "Failed to start device flow"))
    return flow


def complete_device_flow(flow: dict[str, Any]) -> None:
    """Block, polling until the user authorizes (or the flow expires/fails).

    Saves the token cache on success. Raises MicrosoftGraphError on failure/expiry.
    """
    cache = _load_cache()
    app = _app(cache)
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise MicrosoftGraphError(result.get("error_description", "Device flow did not complete"))
    _save_cache(cache)


def is_authenticated() -> bool:
    """True if a valid (or silently refreshable) cached token exists."""
    try:
        cache = _load_cache()
        app = _app(cache)
    except MicrosoftGraphNotConfiguredError:
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
        raise MicrosoftGraphAuthRequiredError("Not authenticated yet — run the device code flow first.")
    result = app.acquire_token_silent(SCOPES, account=accounts[0])
    _save_cache(cache)
    if not result or "access_token" not in result:
        raise MicrosoftGraphAuthRequiredError("Cached token expired or revoked — re-run the device code flow.")
    return result["access_token"]


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_access_token()}"}


def graph_get(path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        r = requests.get(f"{GRAPH_BASE}{path}", headers=_headers(), params=params or {}, timeout=10)
    except requests.RequestException as e:
        raise MicrosoftGraphError(f"Graph API request failed: {e}") from e
    return _handle_response(r)


def graph_post(path: str, json_body: dict[str, Any]) -> dict[str, Any]:
    try:
        r = requests.post(f"{GRAPH_BASE}{path}", headers=_headers(), json=json_body, timeout=10)
    except requests.RequestException as e:
        raise MicrosoftGraphError(f"Graph API request failed: {e}") from e
    return _handle_response(r)


def graph_patch(path: str, json_body: dict[str, Any]) -> dict[str, Any]:
    try:
        r = requests.patch(f"{GRAPH_BASE}{path}", headers=_headers(), json=json_body, timeout=10)
    except requests.RequestException as e:
        raise MicrosoftGraphError(f"Graph API request failed: {e}") from e
    return _handle_response(r)


def graph_delete(path: str) -> None:
    try:
        r = requests.delete(f"{GRAPH_BASE}{path}", headers=_headers(), timeout=10)
    except requests.RequestException as e:
        raise MicrosoftGraphError(f"Graph API request failed: {e}") from e
    if r.status_code not in (200, 202, 204):
        raise MicrosoftGraphError(f"Graph API error {r.status_code}: {r.text[:300]}")


def _handle_response(r: requests.Response) -> dict[str, Any]:
    if r.status_code not in (200, 201):
        raise MicrosoftGraphError(f"Graph API error {r.status_code}: {r.text[:300]}")
    return r.json() if r.text else {}
