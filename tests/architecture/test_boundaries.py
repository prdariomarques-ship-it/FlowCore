"""Architectural boundary tests ensuring layer isolation and Protocol runtime checkability."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import _ProtocolMeta

import pytest

import darius.interfaces as interfaces

INTERFACES_DIR = Path(__file__).resolve().parent.parent.parent / "darius" / "interfaces"
NOTIFICATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "darius" / "notifications"
JOBS_DIR = Path(__file__).resolve().parent.parent.parent / "darius" / "jobs"


def _extract_imported_modules(file_path: Path) -> list[str]:
    """Parse AST and return list of all top-level imported module names."""
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.append(node.module)
    return imported


class TestHexagonalBoundaries:
    """Validate that ports/interfaces maintain strict hexagonal layer isolation."""

    def test_interfaces_have_no_outward_or_runtime_dependencies(self):
        """darius/interfaces/ must only import stdlib, pydantic, or sibling interfaces.

        It must never import runtime.*, agents.*, api.*, or storage.*.
        """
        forbidden_roots = {"runtime", "agents", "api", "storage", "capability", "flows"}

        for py_file in INTERFACES_DIR.glob("*.py"):
            imports = _extract_imported_modules(py_file)
            for imp in imports:
                root_module = imp.split(".")[0]
                assert root_module not in forbidden_roots, (
                    f"Violation in {py_file.name}: Interface illegally imports from "
                    f"'{imp}'. Interfaces must remain pure port contracts."
                )

    def test_notifications_have_no_core_runtime_dependencies(self):
        """darius/notifications/ must not depend on agents core (Task, State, Agent Core)."""
        forbidden_modules = {"agents.contracts", "runtime.agent", "agents.base_agent"}

        for py_file in NOTIFICATIONS_DIR.glob("*.py"):
            imports = _extract_imported_modules(py_file)
            for imp in imports:
                assert imp not in forbidden_modules, (
                    f"Violation in {py_file.name}: Notifications illegally imports "
                    f"Core Runtime module '{imp}'."
                )

    def test_jobs_have_no_core_runtime_dependencies(self):
        """darius/jobs/ must not import core task or agent state machine."""
        forbidden_modules = {"agents.contracts", "runtime.agent"}

        for py_file in JOBS_DIR.glob("*.py"):
            imports = _extract_imported_modules(py_file)
            for imp in imports:
                assert imp not in forbidden_modules, (
                    f"Violation in {py_file.name}: Jobs illegally imports "
                    f"Core Runtime module '{imp}'."
                )


class TestProtocolRuntimeCheckability:
    """Ensure all Protocols defined in darius.interfaces are @runtime_checkable."""

    @pytest.mark.parametrize(
        "protocol_name",
        [
            "LLMAdapter",
            "ToolAdapter",
            "MCPAdapter",
            "MemoryAdapter",
            "SkillAdapter",
            "NotificationChannelAdapter",
        ],
    )
    def test_protocol_is_runtime_checkable(self, protocol_name: str):
        proto = getattr(interfaces, protocol_name)
        assert isinstance(proto, _ProtocolMeta), f"{protocol_name} must be a typing.Protocol"
        # @runtime_checkable adds _is_runtime_protocol attribute
        assert getattr(proto, "_is_runtime_protocol", False) is True, (
            f"Protocol {protocol_name} must be decorated with @runtime_checkable"
        )
