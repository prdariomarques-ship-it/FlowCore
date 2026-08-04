from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any
from .capability_registry import CapabilityRegistry
from .runtime_serializer import RuntimeSerializer


class TripleContractManager:
    """Manager to generate, coordinate, and maintain all three versioned contracts of the FlowCore platform."""

    def __init__(self, workspace_path: Path):
        self.workspace_path = Path(workspace_path).resolve()
        self.capability_registry = CapabilityRegistry(self.workspace_path)
        self.runtime_serializer = RuntimeSerializer()

    def generate_all_contracts(self, frame: Any) -> Dict[str, Path]:
        """Generate all three contract JSON files and return their target Paths."""
        # 1. Write flowcore.capabilities.json
        capabilities_path = self.capability_registry.write_capabilities_file(self.workspace_path)

        # 2. Write flowcore.runtime.json
        runtime_data = self.runtime_serializer.serialize(self.workspace_path)
        runtime_path = self.workspace_path / "flowcore.runtime.json"

        # 3. Write flowcore.context.json
        context_path = self.workspace_path / "flowcore.context.json"
        context_data = {
            "$schema": "https://flowcore.io/schemas/context.v1.json",
            "schema_version": "1.0",

            "runtime": {
                "status": frame.status,
                "engine": "FlowCore Runtime",
                "platform": "Termux",
                "workspace": str(frame.workspace_root) if frame.workspace_root else ""
            },

            "project": {
                "name": frame.project,
                "language": frame.language,
                "type": frame.type
            },

            "environment": {
                "python": True,
                "git": True,
                "termux": True,
                "docker": False,
                "adb": False,
                "oracle_cli": False
            },

            "capabilities": {
                "python": True,
                "sqlite": True,
                "daemon": True,
                "doctor": True,
                "context_engine": True
            },

            "workspace": {
                "validated": frame.validated,
                "multiple_projects": False,
                "project_count": 1
            },

            "health": {
                "status": "HEALTHY",
                "last_check": runtime_data.get("health", {}).get("last_check", "")
            }
        }

        with open(context_path, "w", encoding="utf-8") as f:
            json.dump(context_data, f, indent=2, ensure_ascii=False)

        return {
            "capabilities": capabilities_path,
            "runtime": runtime_path,
            "context": context_path
        }
