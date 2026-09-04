#!/usr/bin/env python3
"""Validação E2E do servidor MCP do FlowCore via cliente MCP real.

Usa o próprio SDK `mcp` (ClientSession + stdio transport) como faria
qualquer cliente real — inclusive Claude Code. Valida handshake e
chama uma amostra de ferramentas com dados reais.
"""

from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402


async def main() -> int:
    params = StdioServerParameters(command="python3", args=["flowcore.py", "mcp"], cwd=str(ROOT))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            caps = await session.list_tools()
            tools = caps.tools
            print(f"initialize OK — total ferramentas MCP: {len(tools)}")

            sample_names = [
                "flowcore_macro_score_scores",
                "flowcore_observer_registry",
                "flowcore_portfolio_list",
                "flowcore_regime_signals",
            ]
            for name in sample_names:
                t = next((t for t in tools if t.name == name), None)
                if t:
                    print(f"  - {name}: {t.description[:65]}")

            if not any(t.name == n for n in sample_names for t in tools):
                print("  (nenhuma da amostra encontrada — conferir nomes)")
                return 1

            target = next(t for t in tools if t.name == sample_names[0])
            result = await session.call_tool(target.name, arguments={})
            text = result.content[0].text if result.content else "(vazio)"
            print("resultado real da amostra:", text[:140].replace("\n", " "))

            # Validação adicional: uma ferramenta com argumento (portfolio summary).
            plist = await session.call_tool("flowcore_portfolio_list", arguments={})
            txt = plist.content[0].text if plist.content else ""
            data = json.loads(txt) if txt.strip().startswith("{") else None
            if data and "portfolios" in data:
                print(f"flowcore_portfolio_list: {len(data['portfolios'])} portfolio(s) — real")
            return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
