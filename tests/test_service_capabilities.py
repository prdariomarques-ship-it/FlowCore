"""Tests for service.py's Android capability wrappers (Sprint 17, Milestone 1).

CapabilityRegistry.call is mocked throughout — these test that service.py
calls the registry with the right capability name/args and returns
CapabilityResult.to_dict(), not the capability's own real behavior (that's
covered directly in tests/test_capability.py).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ok(data):
    from capability.adapters.base import CapabilityResult

    return CapabilityResult.ok(data, "test")


class TestServiceCapabilityWrappers:
    def test_get_battery_calls_registry_with_right_capability(self):
        import service

        with patch.object(service._registry, "call", return_value=_ok({"level": 80})) as m:
            result = asyncio.run(service.get_battery())
        m.assert_called_once_with("getBattery")
        assert result == {"success": True, "data": {"level": 80}, "bridge": "test"}

    def test_get_wifi_info_calls_getNetworkInfo(self):
        import service

        with patch.object(service._registry, "call", return_value=_ok({"ssid": "x"})) as m:
            asyncio.run(service.get_wifi_info())
        m.assert_called_once_with("getNetworkInfo")

    def test_get_disk_usage_passes_path(self):
        import service

        with patch.object(service._registry, "call", return_value=_ok({"total": "1G"})) as m:
            asyncio.run(service.get_disk_usage("/custom"))
        m.assert_called_once_with("getDiskUsage", "/custom")

    def test_get_disk_usage_default_path(self):
        import service

        with patch.object(service._registry, "call", return_value=_ok({})) as m:
            asyncio.run(service.get_disk_usage())
        m.assert_called_once_with("getDiskUsage", "/data")

    def test_get_clipboard_calls_registry(self):
        import service

        with patch.object(service._registry, "call", return_value=_ok({"text": "hi"})) as m:
            result = asyncio.run(service.get_clipboard())
        m.assert_called_once_with("getClipboard")
        assert result["data"]["text"] == "hi"

    def test_set_clipboard_passes_text(self):
        import service

        with patch.object(service._registry, "call", return_value=_ok({"set": True})) as m:
            asyncio.run(service.set_clipboard("hello"))
        m.assert_called_once_with("setClipboard", "hello")

    def test_send_notification_passes_title_and_message(self):
        import service

        with patch.object(service._registry, "call", return_value=_ok({"sent": True})) as m:
            asyncio.run(service.send_notification("Title", "Body"))
        m.assert_called_once_with("sendNotification", "Title", "Body")

    def test_list_installed_apps_calls_registry(self):
        import service

        with patch.object(service._registry, "call", return_value=_ok({"count": 0, "packages": []})) as m:
            asyncio.run(service.list_installed_apps())
        m.assert_called_once_with("listInstalledApps")

    def test_get_android_info_calls_registry(self):
        import service

        with patch.object(service._registry, "call", return_value=_ok({"release": "14"})) as m:
            asyncio.run(service.get_android_info())
        m.assert_called_once_with("getAndroidInfo")

    def test_failure_result_propagates(self):
        import service
        from capability.adapters.base import CapabilityResult

        fail = CapabilityResult.fail("nope", "test", corrective_action="do X")
        with patch.object(service._registry, "call", return_value=fail):
            result = asyncio.run(service.get_battery())
        assert result["success"] is False
        assert result["corrective_action"] == "do X"
