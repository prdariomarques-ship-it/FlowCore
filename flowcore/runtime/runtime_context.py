from __future__ import annotations

import json
import datetime
from pathlib import Path
from typing import Dict, Any, List


class RuntimeContext:
    """Manages system configurations and compiles the flowcore.runtime.passport.json."""

    def __init__(self, workspace_path: Path):
        self.workspace_path = Path(workspace_path).resolve()
        self.runtime_id = "termux_runtime_01"
        self.runtime_version = "4.0"
        self.platform = "Android/Termux"
        self.providers: List[str] = ["battery", "wifi", "clipboard", "python"]
        self.permissions: Dict[str, str] = {"storage": "GRANTED", "termux_api": "GRANTED"}
        self.capabilities: List[str] = ["getBattery", "getWifi", "installPythonPackage"]
        self.status = "NOT_READY"
        self.boot_time = datetime.datetime.utcnow().isoformat() + "Z"
        self.last_health_check = self.boot_time

    def write_passport(self) -> Path:
        """Write the runtime passport JSON file to the workspace root."""
        passport_data = {
            "$schema": "https://flowcore.io/schemas/runtime-passport.v1.json",
            "runtime_id": self.runtime_id,
            "runtime_version": self.runtime_version,
            "platform": self.platform,
            "providers": self.providers,
            "health": {
                "status": "HEALTHY",
                "disk": "OK",
                "memory": "OK"
            },
            "permissions": self.permissions,
            "capabilities": self.capabilities,
            "boot_time": self.boot_time,
            "last_health_check": self.last_health_check,
            "status": self.status
        }

        file_path = self.workspace_path / "flowcore.runtime.passport.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(passport_data, f, indent=2, ensure_ascii=False)

        return file_path
