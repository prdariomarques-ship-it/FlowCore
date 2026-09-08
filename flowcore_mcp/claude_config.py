"""Print the Claude Desktop / Claude Code configuration snippet for FlowCore MCP."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def print_claude_config(flowcore_root: str | None = None) -> None:
    root = flowcore_root or str(Path(__file__).resolve().parent.parent)
    config = {
        "mcpServers": {
            "flowcore": {
                "command": "python3",
                "args": [f"{root}/flowcore.py", "mcp"],
                "env": {},
            }
        }
    }
    print("Add to your claude_desktop_config.json:")
    print(json.dumps(config, indent=2))


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else None
    print_claude_config(root)
