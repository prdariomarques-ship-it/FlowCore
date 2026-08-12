"""Agent Engine -- natural language -> tool selection -> real execution.

Public surface for runtime/agent/. Mirrors runtime/narrative/'s __init__.py
shape: re-export the engine and its data model, keep the package's
internal module layout (models/prompt/engine) private.
"""

from __future__ import annotations

from runtime.agent.engine import AgentEngine
from runtime.agent.models import AgentResult, ToolSpec

__all__ = ["AgentEngine", "AgentResult", "ToolSpec"]
