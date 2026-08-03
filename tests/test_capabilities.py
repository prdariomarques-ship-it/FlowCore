from __future__ import annotations

import json

from fastapi.testclient import TestClient

from api.router import create_app
from capabilities.registry import CAPABILITIES, CapabilityStatus, capability
from runtime.core import detect_platform


def test_capabilities_never_return_mock_and_serialize() -> None:
    for name in CAPABILITIES:
        result = capability(name)
        assert result.status != CapabilityStatus.MOCK
        json.dumps(result.to_dict())


def test_android_capabilities_are_unavailable_outside_android() -> None:
    if detect_platform()["android"]:
        return
    for name in ("battery", "wifi"):
        result = capability(name)
        assert result.status == CapabilityStatus.NOT_IMPLEMENTED
        assert result.error


def test_capability_endpoints_return_envelopes() -> None:
    client = TestClient(create_app())
    for name in (
        "status",
        "doctor",
        "battery",
        "wifi",
        "storage",
        "runtime",
        "passport",
        "context",
    ):
        response = client.get(f"/{name}")
        assert response.status_code == 200
        payload = response.json()
        assert {
            "name",
            "status",
            "provider",
            "data",
            "error",
            "duration_ms",
            "timestamp",
        } <= payload.keys()
