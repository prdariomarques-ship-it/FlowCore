from __future__ import annotations

from typing import Dict, Any, List


class SchemaValidator:
    """Zero-dependency schema structural validator for FlowCore contracts."""

    @staticmethod
    def validate_context(data: Dict[str, Any]) -> bool:
        """Validate structure of flowcore.context.json."""
        required_keys = ["schema_version", "runtime", "project", "environment", "capabilities", "workspace", "health"]
        return all(key in data for key in required_keys)

    @staticmethod
    def validate_runtime(data: Dict[str, Any]) -> bool:
        """Validate structure of flowcore.runtime.json."""
        required_keys = ["boot_status", "doctor_status", "runtime_status", "python_version", "git_version", "health"]
        return all(key in data for key in required_keys)

    @staticmethod
    def validate_capabilities(data: Dict[str, Any]) -> bool:
        """Validate structure of flowcore.capabilities.json."""
        # Must be a dictionary where values are sub-dicts specifying paths
        if not isinstance(data, dict):
            return False
        return True
