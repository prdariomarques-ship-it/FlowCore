"""Tool Registry and Audit Logger for FlowCore Agentic Platform."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime.tools.base import BaseTool, RiskLevel

STORAGE_DIR = Path(__file__).resolve().parent.parent.parent / "storage"
AUDIT_FILE = STORAGE_DIR / "tool_audit.json"


class ToolRegistry:
    def __init__(self, audit_file: Path = AUDIT_FILE) -> None:
        self._tools: Dict[str, BaseTool] = {}
        self.audit_file = audit_file
        self.audit_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.audit_file.exists():
            self._save_audit([])

    def _load_audit(self) -> List[Dict[str, Any]]:
        try:
            with open(self.audit_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_audit(self, logs: List[Dict[str, Any]]) -> None:
        with open(self.audit_file, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    def execute(
        self,
        tool_name: str,
        kwargs: Dict[str, Any],
        agent_id: str = "system",
        granted_permissions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        tool = self.get(tool_name)
        if not tool:
            raise KeyError(f"Tool '{tool_name}' not found.")

        # Permission check
        permissions = granted_permissions or ["*"]
        if "*" not in permissions and tool.permission not in permissions:
            raise PermissionError(f"Agent '{agent_id}' lacks permission '{tool.permission}' for tool '{tool_name}'.")

        start_time = time.time()
        status = "SUCCESS"
        result = None
        error_msg = None

        try:
            result = tool.run(**kwargs)
        except Exception as e:
            status = "FAILED"
            error_msg = str(e)
            raise e
        finally:
            elapsed = time.time() - start_time
            audit_log = self._load_audit()
            audit_log.append({
                "timestamp": time.time(),
                "agent_id": agent_id,
                "tool_name": tool_name,
                "risk_level": tool.risk_level.value,
                "kwargs": kwargs,
                "status": status,
                "elapsed_seconds": round(elapsed, 4),
                "error": error_msg,
            })
            self._save_audit(audit_log)

        return result


_registry_instance = ToolRegistry()

def get_tool_registry() -> ToolRegistry:
    return _registry_instance
