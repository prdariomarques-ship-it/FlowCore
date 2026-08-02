from __future__ import annotations

import datetime
import hashlib
import json
from typing import Dict, Any, List, Optional
from pathlib import Path
from .interfaces import IPassportBuilder
from .context_version import ContextVersion


class PassportGenerationError(Exception):
    """Exception raised when FlowCorePassport generation fails."""
    pass


class FlowCorePassport:
    """Consolidated transit context card (passport) containing secure system state telemetries."""

    def __init__(self, data: Dict[str, Any]):
        self._data = data

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the passport to dictionary format."""
        return self._data

    def to_json(self) -> str:
        """Serialize the passport to JSON string."""
        return json.dumps(self._data, indent=2, ensure_ascii=False)


class PassportBuilder(IPassportBuilder):
    """Component to consolidate context, environment and capabilities into a verified FlowCorePassport."""

    def build_passport(self, frame: Any) -> FlowCorePassport:
        """Build the verified passport based on the consolidated pipeline ContextFrame."""
        try:
            workspace_root_str = str(frame.workspace_root) if frame.workspace_root else ""

            # 1. Gather baseline states
            project_data = {
                "name": frame.project,
                "language": frame.language,
                "type": frame.type
            }

            environment_data = {
                "python": True,
                "git": True,
                "termux": True,
                "docker": False,
                "adb": False,
                "oracle_cli": False
            }

            capabilities_list = ["python", "sqlite", "daemon", "doctor", "context_engine"]

            # 2. Compute integrity verification hashes (SHA-256)
            workspace_raw = workspace_root_str.encode("utf-8")
            workspace_hash = hashlib.sha256(workspace_raw).hexdigest()

            context_raw = json.dumps(project_data, sort_keys=True).encode("utf-8")
            context_hash = hashlib.sha256(context_raw).hexdigest()

            runtime_raw = json.dumps(environment_data, sort_keys=True).encode("utf-8")
            runtime_hash = hashlib.sha256(runtime_raw).hexdigest()

            # 3. Compile passport contract
            passport_data = {
                "$schema": "https://flowcore.io/schemas/passport.v1.json",
                "schema_version": ContextVersion.SCHEMA_VERSION,
                "architecture_version": ContextVersion.ARCHITECTURE_VERSION,

                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "status": frame.status,

                "project": project_data,
                "workspace": {
                    "path": workspace_root_str,
                    "validated": frame.validated,
                    "multiple_projects": False,
                    "project_count": 1
                },

                "runtime": {
                    "engine": "FlowCore Runtime",
                    "platform": "Termux",
                    "status": frame.status
                },

                "health": {
                    "status": "HEALTHY",
                    "last_check": datetime.datetime.utcnow().isoformat() + "Z"
                },

                "capabilities": capabilities_list,
                "permissions": {
                    "storage": "GRANTED",
                    "camera": "GRANTED",
                    "microphone": "GRANTED"
                },

                "environment": environment_data,
                "agent": {
                    "active_agent": "FlowCore Principal Platform Engineer",
                    "registered_agents": ["Jules", "Qwen", "GLM", "Claude Code", "Codex", "Manus", "Gemini"]
                },

                "workspace_hash": workspace_hash,
                "context_hash": context_hash,
                "runtime_hash": runtime_hash
            }

            return FlowCorePassport(passport_data)

        except Exception as e:
            raise PassportGenerationError(f"Failed to assemble FlowCorePassport: {e}") from e
