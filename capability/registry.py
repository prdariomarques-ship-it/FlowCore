"""FlowCore Capability Registry — maps capability names to concrete adapters.

The registry holds all registered adapters and exposes `get(capability_name)`
which returns the highest-priority available adapter that implements the
requested capability.

Usage::

    registry = CapabilityRegistry()
    adapter = registry.get("getBattery")
    if adapter:
        result = adapter.get_battery()
"""

from __future__ import annotations

from typing import Callable

from capability.adapters.base import CapabilityAdapter, CapabilityResult
from capability.adapters.android import ANDROID_ADAPTERS
from capability.adapters.termux import TERMUX_ADAPTERS
from capability.adapters.linux import LinuxAdapter

# ── Capability → method name mapping ─────────────────────────────────────────

_CAPABILITY_METHOD: dict[str, str] = {
    # Android-specific
    "getBattery": "get_battery",
    "getClipboard": "get_clipboard",
    "setClipboard": "set_clipboard",
    "sendNotification": "send_notification",
    "getNetworkInfo": "get_network_info",
    "getWifiScan": "get_wifi_scan",
    "getBluetoothState": "get_bluetooth_state",
    "getLocation": "get_location",
    "takePhoto": "take_photo",
    "recordAudio": "record_audio",
    "vibrate": "vibrate",
    "torch": "torch",
    "openUrl": "open_url",
    "shareFile": "share_file",
    "checkPermission": "check_permission",
    "listPermissions": "list_permissions",
    "acquireWakeLock": "acquire_wakelock",
    "releaseWakeLock": "release_wakelock",
    "getAndroidInfo": "get_android_info",
    # Termux / Linux
    "runPython": "run_python",
    "runGit": "run_git",
    "runSSH": "run_ssh",
    "runSQLite": "run_sqlite",
    "runShell": "run_shell",
    "installPackage": "install_package",
    "readFile": "read_file",
    "writeFile": "write_file",
    "listDirectory": "list_directory",
    "httpRequest": "http_get",
    "startService": "start_service",
    "stopService": "stop_service",
    "listServices": "list_services",
    "scheduleJob": "schedule_job",
}


def _default_adapters() -> list[CapabilityAdapter]:
    """Instantiate all adapters in priority order (highest first)."""
    instances: list[CapabilityAdapter] = []
    for cls in ANDROID_ADAPTERS:
        instances.append(cls())
    for cls in TERMUX_ADAPTERS:
        instances.append(cls())
    instances.append(LinuxAdapter())
    return instances


class CapabilityRegistry:
    """Maintains the ordered adapter list and resolves capability requests."""

    def __init__(self, adapters: list[CapabilityAdapter] | None = None) -> None:
        if adapters is None:
            adapters = _default_adapters()
        self._adapters: list[CapabilityAdapter] = sorted(adapters, key=lambda a: a.priority, reverse=True)
        self._available_cache: dict[str, bool] = {}

    def available_adapters(self) -> list[CapabilityAdapter]:
        """Return adapters that pass is_available(), in priority order."""
        result = []
        for adapter in self._adapters:
            key = adapter.name
            if key not in self._available_cache:
                self._available_cache[key] = adapter.is_available()
            if self._available_cache[key]:
                result.append(adapter)
        return result

    def get(self, capability: str) -> CapabilityAdapter | None:
        """Return highest-priority available adapter that overrides *capability*."""
        method_name = _CAPABILITY_METHOD.get(capability)
        if method_name is None:
            return None
        for adapter in self.available_adapters():
            if not _is_base_stub(adapter, method_name):
                return adapter
        return None

    def call(self, capability: str, *args, **kwargs) -> CapabilityResult:
        """Resolve *capability* and call it. Returns fail if nothing handles it."""
        adapter = self.get(capability)
        if adapter is None:
            return CapabilityResult.fail(
                f"No adapter available for '{capability}'",
                "registry",
                reason=f"No installed adapter implements '{capability}'",
                corrective_action="Install Termux:API (pkg install termux-api) or check capability name",
            )
        method: Callable = getattr(adapter, _CAPABILITY_METHOD[capability])
        return method(*args, **kwargs)

    def list_capabilities(self) -> dict[str, str | None]:
        """Return {capability: adapter_name | None} for all known capabilities."""
        return {cap: (a.name if (a := self.get(cap)) else None) for cap in _CAPABILITY_METHOD}

    def capability_names(self) -> list[str]:
        return list(_CAPABILITY_METHOD.keys())

    def invalidate_cache(self) -> None:
        """Force re-evaluation of adapter availability on next call."""
        self._available_cache.clear()

    def __repr__(self) -> str:
        avail = [a.name for a in self.available_adapters()]
        return f"<CapabilityRegistry adapters={avail}>"


def _is_base_stub(adapter: CapabilityAdapter, method_name: str) -> bool:
    """Return True if *method_name* is inherited from CapabilityAdapter (not overridden)."""
    base_method = getattr(CapabilityAdapter, method_name, None)
    adapter_method = getattr(type(adapter), method_name, None)
    return adapter_method is base_method
