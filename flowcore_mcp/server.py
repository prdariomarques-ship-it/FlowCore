"""FlowCore MCP server — exposes FlowCore capabilities via Model Context Protocol.

Transport: stdio (default) for use with Claude Desktop / Claude Code.
Run with: python3 flowcore.py mcp
"""
from __future__ import annotations

import anyio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import ListToolsResult, CallToolRequestParams

from flowcore_mcp.tools import FLOWCORE_TOOLS, dispatch


class FlowCoreMCPServer:
    """Wraps the MCP Server with FlowCore tool handlers."""

    def __init__(self, version: str = "0.1.0") -> None:
        self._version = version
        self._server = Server(
            name="flowcore",
            version=version,
            description="FlowCore — mobile-first AI agent runtime on Android/Termux",
            on_list_tools=self._list_tools,
            on_call_tool=self._call_tool,
        )

    async def _list_tools(self, _ctx, _params) -> ListToolsResult:
        return ListToolsResult(tools=FLOWCORE_TOOLS)

    async def _call_tool(self, _ctx, params: CallToolRequestParams):
        args = dict(params.arguments or {})
        return dispatch(params.name, args)

    async def serve_stdio(self) -> None:
        """Run the MCP server over stdin/stdout (for Claude Desktop integration)."""
        init_options = self._server.create_initialization_options()
        async with stdio_server() as (read_stream, write_stream):
            await self._server.run(read_stream, write_stream, init_options)


def run_stdio(version: str = "0.1.0") -> None:
    """Entry point: run FlowCore MCP server over stdio."""
    srv = FlowCoreMCPServer(version=version)
    anyio.run(srv.serve_stdio)
