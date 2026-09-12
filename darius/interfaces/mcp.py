"""Model Context Protocol (MCP) Adapter Interface for DARIUS OSS."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from darius.interfaces.tools import ToolDefinition, ToolExecutionResult


class MCPResource(BaseModel):
    """Resource exposed via the Model Context Protocol."""

    uri: str
    name: str
    description: str = ""
    mime_type: str = "text/plain"


class MCPPromptArgument(BaseModel):
    """Prompt template argument definition in MCP."""

    name: str
    description: str = ""
    required: bool = True


class MCPPrompt(BaseModel):
    """Prompt template exposed via the Model Context Protocol."""

    name: str
    description: str = ""
    arguments: list[MCPPromptArgument] = Field(default_factory=list)


@runtime_checkable
class MCPAdapter(Protocol):
    """Port interface for bidirectional Model Context Protocol clients/servers."""

    async def list_tools(self) -> list[ToolDefinition]:
        """Discover tools exposed across the MCP boundary."""
        ...

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolExecutionResult:
        """Invoke a tool across the MCP protocol boundary."""
        ...

    async def list_resources(self) -> list[MCPResource]:
        """List accessible resources from the MCP server."""
        ...

    async def read_resource(self, uri: str) -> str:
        """Read content from an MCP resource URI."""
        ...

    async def health(self) -> dict[str, Any]:
        """Verify protocol connection health and availability."""
        ...
