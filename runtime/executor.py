"""FlowCore — Flow step executor.

Runs a Flow's steps in order, stopping at the first failure. Deliberately
minimal: no queue, no worker pool, no concurrency limit, no retry — the
Sprint 14-era `executor/engine.py` had all of that for arbitrary
concurrent async tasks, but a Flow is one sequential pipeline run on
demand for a single user. That machinery was removed as unused
complexity in Sprint 14; this module does not reintroduce it.

Every action a step can perform is a thin wrapper around an existing
service.py function — a step never runs arbitrary code, only FlowCore's
own already-reviewed capabilities.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

import service

ACTIONS: dict[str, Callable[[dict[str, Any]], Awaitable[Any]]] = {
    "note": lambda p: service.add_note(p["text"], "note"),
    "todo": lambda p: service.add_note(p["text"], "todo"),
    "agenda": lambda p: service.add_note(p["text"], "agenda"),
    "ask": lambda p: service.ask(p["question"], timeout=p.get("timeout")),
    "search": lambda p: service.search(p["query"]),
    "import_markdown": lambda p: service.import_markdown(p["filepath"]),
}


async def run_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run each step in order. Stops at the first failure or unknown action.

    Returns one result dict per attempted step:
    {"action": str, "status": "completed" | "failed", "output": Any} or
    {"action": str, "status": "failed", "error": str}.
    Steps after a failure are not attempted (not included in the result).
    """
    results: list[dict[str, Any]] = []
    for step in steps:
        action = step.get("action")
        handler = ACTIONS.get(action)
        if handler is None:
            results.append({"action": action, "status": "failed", "error": f"Unknown action: {action!r}"})
            break
        try:
            output = await handler(step.get("params", {}))
            results.append({"action": action, "status": "completed", "output": output})
        except Exception as e:
            results.append({"action": action, "status": "failed", "error": str(e)})
            break
    return results
