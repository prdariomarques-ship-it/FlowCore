from __future__ import annotations

import os
import shutil
from typing import Dict, Any, List, Optional
from pathlib import Path


class RuntimeManager:
    """Manages discovery, registration, selection, prioritization, and failover of active Runtimes."""

    def __init__(self, workspace_path: Path):
        self.workspace_path = Path(workspace_path).resolve()
        self._runtimes: Dict[str, Any] = {}
        self._active_runtime_name: Optional[str] = None

        # Self-register known runtimes
        self.register_runtime("android", AndroidRuntime())
        self.register_runtime("termux", TermuxRuntime())

        # Discover and select best runtime automatically
        self.select_best_runtime()

    def register_runtime(self, name: str, runtime: Any) -> None:
        """Register a runtime into the manager."""
        self._runtimes[name] = runtime

    def get_runtime(self, name: str) -> Any:
        """Get registered runtime by name."""
        return self._runtimes.get(name)

    def select_best_runtime(self) -> str:
        """Prioritization strategy: choose Termux if PREFIX exists, fallback to Android or basic shell."""
        if os.environ.get("PREFIX"):
            self._active_runtime_name = "termux"
        else:
            self._active_runtime_name = "android"
        return self._active_runtime_name

    def get_active_runtime(self) -> Any:
        """Get currently active runtime."""
        return self._runtimes.get(self._active_runtime_name)

    def switch_runtime(self, name: str) -> None:
        """Switch active runtime manually."""
        if name in self._runtimes:
            self._active_runtime_name = name


class AndroidRuntime:
    """Specialized Android Runtime implementing the base execute capability flow."""

    def __init__(self):
        self.platform = "Android"
        self.status = "NOT_READY"

    def boot(self) -> str:
        self.status = "READY"
        return self.status

    def execute_capability(self, capability: str, **kwargs) -> Any:
        # For Android host execution validation
        if capability == "getBattery":
            # If termux-api exists on Android PATH, call it. Otherwise, return NOT_IMPLEMENTED for real hardware checks
            if shutil.which("termux-battery-status"):
                from .termux.termux_api import TermuxApiProvider
                return TermuxApiProvider().get_battery()
            return {
                "status": "NOT_IMPLEMENTED",
                "error": "Android BatteryManager requires Termux:API companion binary to run."
            }
        elif capability == "getWifi":
            if shutil.which("termux-wifi-connectioninfo"):
                from .termux.termux_api import TermuxApiProvider
                return TermuxApiProvider().get_wifi()
            return {
                "status": "NOT_IMPLEMENTED",
                "error": "Android WifiManager requires Termux:API companion binary to run."
            }
        raise NotImplementedError(f"AndroidRuntime does not implement capability: {capability}")


class TermuxRuntime:
    """Specialized Termux Runtime representing OS Local commands in Android's Termux Linux."""

    def __init__(self):
        self.platform = "Termux"
        self.status = "NOT_READY"
        from .termux.termux_api import TermuxApiProvider
        self.provider = TermuxApiProvider()

    def boot(self) -> str:
        self.status = "READY"
        return self.status

    def execute_capability(self, capability: str, **kwargs) -> Any:
        if capability == "getBattery":
            return self.provider.get_battery()
        elif capability == "getWifi":
            return self.provider.get_wifi()
        elif capability == "getLocation":
            return self.provider.get_location()
        elif capability == "getCameraInfo":
            return self.provider.get_camera_info()
        elif capability == "getClipboard":
            return self.provider.get_clipboard()
        elif capability == "getStorage":
            return self.provider.get_storage()
        elif capability == "getTelephonyDeviceInfo":
            return self.provider.get_telephony_deviceinfo()
        elif capability == "getSensor":
            return self.provider.get_sensor()
        elif capability == "getNotification":
            title = kwargs.get("title", "FlowCore")
            content = kwargs.get("content", "Active")
            return self.provider.get_notification(title, content)
        elif capability == "installPythonPackage":
            # Delegate to python provider
            from .termux.python import TermuxPythonProvider
            package = kwargs.get("package", "numpy")
            return TermuxPythonProvider().install_package(package)

        raise NotImplementedError(f"TermuxRuntime does not implement capability: {capability}")
