"""Hexagonal Architecture Boundary Interfaces and Protocols for DARIUS OSS."""

from __future__ import annotations

from darius.interfaces.llm import (
    LLMAdapter,
    LLMMessage,
    LLMResponse,
    LLMUsage,
)
from darius.interfaces.mcp import (
    MCPAdapter,
    MCPPrompt,
    MCPPromptArgument,
    MCPResource,
)
from darius.interfaces.memory import (
    MemoryAdapter,
    MemoryEntry,
    MemorySearchResult,
)
from darius.interfaces.notifications import (
    NotificationChannelAdapter,
    NotificationDeliveryResult,
    NotificationMessage,
)
from darius.interfaces.skills import (
    SkillAdapter,
    SkillManifest,
)
from darius.interfaces.tools import (
    ToolAdapter,
    ToolDefinition,
    ToolExecutionResult,
    ToolParameter,
)

__all__ = [
    # LLM
    "LLMAdapter",
    "LLMMessage",
    "LLMResponse",
    "LLMUsage",
    # Tools
    "ToolAdapter",
    "ToolDefinition",
    "ToolExecutionResult",
    "ToolParameter",
    # MCP
    "MCPAdapter",
    "MCPPrompt",
    "MCPPromptArgument",
    "MCPResource",
    # Memory
    "MemoryAdapter",
    "MemoryEntry",
    "MemorySearchResult",
    # Skills
    "SkillAdapter",
    "SkillManifest",
    # Notifications
    "NotificationChannelAdapter",
    "NotificationDeliveryResult",
    "NotificationMessage",
]
