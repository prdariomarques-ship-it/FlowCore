"""FlowCore Capability Registry — maps capability names to concrete adapters.

The registry holds all registered adapters and exposes a single
`get(capability_name)` method that returns the highest-priority adapter
that both (a) is available on this host and (b) implements the requested
capability.

Usage::

    registry = CapabilityRegistry()
    adapter = registry.get("getBattery")
    if adapter:
        result = adapter.get_battery()
"""
from __future__ import annotations

from typing import Callable

from capability.adapters.base import CapabilityAdapter, CapabilityResult
from capability.adapters.android import AndroidAdapter
from capability.adapters.termux import TermuxAdapter
from capability.adapters.linux import LinuxAdapter

# Map capability name → method name on the adapter
_CAPABILITY_METHOD: dict[str, str] = {
    "getBattery":        "get_battery",
    "getClipboard":      "get_clipboard",
    "setClipboard":      "set_clipboard",
    "sendNotification":  "send_notification",
    "getNetworkInfo":    "get_network_info",
    "getAndroidInfo":    "get_android_info",
    "runPython":         "run_python",
    "runGit":            "run_git",
    "runSSH":            "run_ssh",
    "installPackage":    "install_package",
    "httpRequest":       "http_get",
    "readFile":          "read_file",
    "writeFile":         "write_file",
    "listDirectory":     "list_directory",
}


class CapabilityRegistry:
    """Maintains the ordered list of adapters and resolves capability requests."""

    def __init__(self, adapters: list[CapabilityAdapter] | None = None) -> None:
        if adapters is None:
            adapters = [AndroidAdapter(), TermuxAdapter(), LinuxAdapter()]
        # Sort descending by priority so highest-priority wins
        self._adapters: list[CapabilityAdapter] = sorted(
            adapters, key=lambda a: a.priority, reverse=True
        )
        # Cache availability checks (they may call subprocesses)
        self._available: dict[str, bool] = {}

    def available_adapters(self) -> list[CapabilityAdapter]:
        """Return adapters that pass is_available(), in priority order."""
        result = []
        for adapter in self._adapters:
            key = adapter.name
            if key not in self._available:
                self._available[key] = adapter.is_available()
            if self._available[key]:
                result.append(adapter)
        return result

    def get(self, capability: str) -> CapabilityAdapter | None:
        """Return the highest-priority available adapter that supports *capability*.

        An adapter "supports" a capability if it has overridden the corresponding
        method (i.e. the method is not the base-class default that always fails).
        """
        method_name = _CAPABILITY_METHOD.get(capability)
        if method_name is None:
            return None

        for adapter in self.available_adapters():
            method = getattr(adapter, method_name, None)
            if method is None:
                continue
            # Skip if this adapter uses the base-class stub (always returns fail)
            if _is_base_stub(adapter, method_name):
                continue
            return adapter

        return None

    def call(self, capability: str, *args, **kwargs) -> CapabilityResult:
        """Resolve *capability* to an adapter and call it.

        Returns a fail result if no adapter handles the capability.
        """
        adapter = self.get(capability)
        if adapter is None:
            return CapabilityResult.fail(
                f"No adapter available for capability '{capability}'", "registry"
            )
        method_name = _CAPABILITY_METHOD[capability]
        method: Callable = getattr(adapter, method_name)
        return method(*args, **kwargs)

    def list_capabilities(self) -> dict[str, str | None]:
        """Return {capability_name: adapter_name | None} for all known capabilities."""
        result: dict[str, str | None] = {}
        for cap in _CAPABILITY_METHOD:
            adapter = self.get(cap)
            result[cap] = adapter.name if adapter else None
        return result

    def __repr__(self) -> str:
        avail = [a.name for a in self.available_adapters()]
        return f"<CapabilityRegistry adapters={avail}>"


def _is_base_stub(adapter: CapabilityAdapter, method_name: str) -> bool:
    """Return True if *method_name* is inherited from CapabilityAdapter (not overridden)."""
    adapter_type = type(adapter)
    base_method = getattr(CapabilityAdapter, method_name, None)
    adapter_method = getattr(adapter_type, method_name, None)
    return adapter_method is base_method
