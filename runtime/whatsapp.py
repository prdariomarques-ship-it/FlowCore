"""FlowCore — WhatsApp integration via Evolution API (Sprint 17, Milestone 4).

Talks to the Evolution API instance already running locally
(docker container `evolution-api`, confirmed on http://127.0.0.1:8080 —
the reason FlowCore's own default port moved to 8090, see
config/local.json) — and specifically to the WhatsApp session already
paired on it. This deliberately never touches instance creation or QR
pairing: v2.2.3 (the version actually running) has a confirmed QR-code
generation bug, which is exactly why the user is migrating this Evolution
API deployment to the official Meta Cloud API elsewhere. Only sending
through the already-paired session avoids that bug entirely — pairing a
*new* instance is explicitly out of scope here.

Per the milestone's own rule ("do not redesign Evolution integration"),
this is a thin, direct REST client — no abstraction over "WhatsApp
providers" in general, since Evolution API is the only backend that
exists to abstract over. Stdlib-adjacent (`requests`, already a
dependency since Sprint 17 Milestone 2's Outlook integration), no new
dependency.
"""

from __future__ import annotations

import os
from typing import Any

import requests

_DEFAULT_API_URL = "http://127.0.0.1:8080"


class WhatsAppError(RuntimeError):
    """Base class for all WhatsApp/Evolution API errors raised by FlowCore."""


class WhatsAppNotConfiguredError(WhatsAppError):
    """EVOLUTION_API_KEY / EVOLUTION_INSTANCE_NAME not set."""


def _api_url() -> str:
    return os.getenv("EVOLUTION_API_URL", _DEFAULT_API_URL).rstrip("/")


def _require_config() -> tuple[str, str]:
    api_key = os.getenv("EVOLUTION_API_KEY")
    instance = os.getenv("EVOLUTION_INSTANCE_NAME")
    if not api_key or not instance:
        raise WhatsAppNotConfiguredError(
            "EVOLUTION_API_KEY / EVOLUTION_INSTANCE_NAME not set. Add the API key and "
            "instance name for your already-paired Evolution API instance to .env "
            f"(server: {_api_url()})."
        )
    return api_key, instance


def check_health() -> dict[str, Any]:
    """Is the Evolution API server itself reachable? No instance/API key needed —
    this is the server's public root endpoint."""
    try:
        r = requests.get(f"{_api_url()}/", timeout=5)
    except requests.RequestException as e:
        raise WhatsAppError(f"Evolution API unreachable: {e}") from e
    if r.status_code != 200:
        raise WhatsAppError(f"Evolution API error {r.status_code}: {r.text[:300]}")
    return r.json()


def get_status() -> dict[str, Any]:
    """Connection state of the configured instance (open/close/connecting)."""
    api_key, instance = _require_config()
    try:
        r = requests.get(
            f"{_api_url()}/instance/connectionState/{instance}",
            headers={"apikey": api_key},
            timeout=5,
        )
    except requests.RequestException as e:
        raise WhatsAppError(f"Evolution API request failed: {e}") from e
    if r.status_code != 200:
        raise WhatsAppError(f"Evolution API error {r.status_code}: {r.text[:300]}")
    return r.json()


def send_message(number: str, text: str) -> dict[str, Any]:
    """Send a text message through the already-paired instance.

    number: destination in international format, digits only (e.g. "5511999999999").
    """
    api_key, instance = _require_config()
    try:
        r = requests.post(
            f"{_api_url()}/message/sendText/{instance}",
            headers={"apikey": api_key},
            json={"number": number, "text": text},
            timeout=10,
        )
    except requests.RequestException as e:
        raise WhatsAppError(f"Evolution API request failed: {e}") from e
    if r.status_code not in (200, 201):
        raise WhatsAppError(f"Evolution API error {r.status_code}: {r.text[:300]}")
    return r.json()
