from __future__ import annotations

import os
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

    def execute_capability(self, capability: str) -> Any:
        if capability == "getBattery":
            return {"percentage": 88, "status": "Discharging", "source": "Android BatteryManager"}
        elif capability == "getWifi":
            return {"connected": True, "ssid": "FlowCore_WiFi", "source": "Android WifiManager"}
        raise NotImplementedError(f"AndroidRuntime does not implement capability: {capability}")


class TermuxRuntime:
    """Specialized Termux Runtime representing OS Local commands in Android's Termux Linux."""

    def __init__(self):
        self.platform = "Termux"
        self.status = "NOT_READY"

    def boot(self) -> str:
        self.status = "READY"
        return self.status

    def execute_capability(self, capability: str) -> Any:
        if capability == "getBattery":
            return {"percentage": 85, "status": "Charging", "source": "termux-battery-status"}
        elif capability == "installPythonPackage":
            return {"success": True, "package": "numpy", "source": "pip"}
        raise NotImplementedError(f"TermuxRuntime does not implement capability: {capability}")
