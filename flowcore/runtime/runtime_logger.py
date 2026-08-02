from __future__ import annotations

import datetime
from typing import Any, Dict


class RuntimeLogger:
    """Telemetry logging module tracking commands, capabilities, outputs, and rollbacks."""

    def __init__(self):
        self.logs: list[Dict[str, Any]] = []

    def log_execution(self, capability: str, result: Any, error: str | None = None) -> Dict[str, Any]:
        """Record runtime operation metrics and status."""
        entry = {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "capability": capability,
            "result": result,
            "error": error,
            "rollback_status": "NONE" if not error else "TRIGGERED"
        }
        self.logs.append(entry)
        return entry
