"""Tool Adapter Protocol and Data Models for DARIUS OSS."""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ToolParameter(BaseModel):
    """Schema specification for an individual tool argument."""

    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None


class ToolDefinition(BaseModel):
    """Manifest describing a tool's capability and execution constraints."""

    name: str
    description: str
    parameters: list[ToolParameter] = Field(default_factory=list)
    permission_level: Literal["read", "write", "execute", "critical"] = "read"


class ToolExecutionResult(BaseModel):
    """Normalized output produced by executing a tool."""

    success: bool
    output: Any = None
    error: str | None = None
    execution_ms: int = 0


@runtime_checkable
class ToolAdapter(Protocol):
    """Port interface for pluggable agent tools and system capabilities."""

    @property
    def definition(self) -> ToolDefinition:
        """Return the tool metadata and schema definition."""
        ...

    async def execute(
        self,
        params: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ToolExecutionResult:
        """Execute the tool with validated arguments within an optional execution context."""
        ...
