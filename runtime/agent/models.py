"""Canonical Agent Engine data model.

A ToolSpec pairs an LLM-facing description (name, description, a
human-readable parameter hint) with the real Python callable that
performs the action -- the "LLM only ever *selects*, FlowCore code
always *executes*" split that runtime/agent/engine.py enforces. handler
is async, called with **arguments parsed straight from the model's JSON
tool call; it either returns a real result dict or raises (ValueError
for "need clarification", anything else for a genuine failure) -- see
engine.py for how each is handled.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field


@dataclass
class ToolSpec:
    name: str
    description: str
    handler: Callable[..., Awaitable[dict]]
    # Parameter name -> human-readable hint shown to the LLM (e.g.
    # "string, obrigatorio"). Deliberately not a JSON Schema validator --
    # the handler itself is the real validation (raises on bad input).
    parameters: dict[str, str] = field(default_factory=dict)


@dataclass
class AgentResult:
    answer: str
    model: str | None
    tool_used: str | None
    tool_result: dict | None = None

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "model": self.model,
            "tool_used": self.tool_used,
            "tool_result": self.tool_result,
        }
