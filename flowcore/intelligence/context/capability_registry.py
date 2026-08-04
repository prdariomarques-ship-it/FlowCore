from __future__ import annotations

import json
from typing import Dict, Any, Optional
from pathlib import Path
from .interfaces import ICapabilityRegistry


class CapabilityNotFoundError(Exception):
    """Exception raised when a requested capability is not registered."""
    pass


class CapabilityRegistry(ICapabilityRegistry):
    """Official FlowCore registry for mapping abstract intentions into platform execution paths."""

    # Official capability mappings
    _DEFAULT_REGISTRY: Dict[str, Dict[str, Any]] = {
        "battery": {
            "android_api": True,
            "termux_api": True,
            "shell": True,
            "description": "Access system power and battery metrics."
        },
        "wifi": {
            "android_api": True,
            "termux_api": False,
            "shell": False,
            "description": "Access Wi-Fi network state and signal strength."
        },
        "camera": {
            "android_api": True,
            "termux_api": True,
            "shell": False,
            "description": "Interface with the physical camera hardware."
        },
        "microphone": {
            "android_api": True,
            "termux_api": True,
            "shell": False,
            "description": "Interface with system audio microphones."
        },
        "filesystem": {
            "android_api": False,
            "termux_api": False,
            "shell": True,
            "description": "Abstract interface to perform secure filesystem operations."
        },
        "install_python_package": {
            "android_api": False,
            "termux_api": False,
            "shell": True,
            "resolver": "pip",
            "description": "Install verified external packages safely into user-space runtime."
        },
        "list_files": {
            "android_api": False,
            "termux_api": False,
            "shell": True,
            "resolver": "filesystem",
            "description": "List files securely within current sandbox."
        },
        "sqlite": {
            "android_api": False,
            "termux_api": False,
            "shell": True,
            "resolver": "sqlite3",
            "description": "Perform robust transactional data storage on local SQLite."
        },
        "mcp": {
            "android_api": False,
            "termux_api": False,
            "shell": True,
            "description": "Interface with Model Context Protocol servers."
        }
    }

    def __init__(self, workspace_path: Optional[Path] = None):
        self.workspace_path = workspace_path
        self._capabilities = self._DEFAULT_REGISTRY.copy()

    def resolve(self, capability_name: str) -> Dict[str, Any]:
        """Resolve a capability by name, returning its available paths and metadata."""
        if capability_name not in self._capabilities:
            raise CapabilityNotFoundError(f"Capability '{capability_name}' is not registered under FlowCore Registry.")
        return self._capabilities[capability_name]

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        """Return the complete capability registry mapping."""
        return self._capabilities

    def write_capabilities_file(self, workspace_root: Path) -> Path:
        """Write flowcore.capabilities.json file to the workspace root."""
        file_path = workspace_root / "flowcore.capabilities.json"

        # Build clean contract JSON
        contract_data = {
            "$schema": "https://flowcore.io/schemas/capabilities.v1.json",
            "schema_version": "1.0",
            "capabilities": {
                name: {
                    "android_api": data.get("android_api", False),
                    "termux_api": data.get("termux_api", False),
                    "shell": data.get("shell", False),
                }
                for name, data in self._capabilities.items()
            }
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(contract_data, f, indent=2, ensure_ascii=False)

        return file_path
