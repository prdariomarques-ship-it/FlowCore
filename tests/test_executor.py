"""Tests for runtime.executor — the Flow step runner.

service.* calls are mocked throughout; this module tests run_steps()'s
own control flow (order, stop-on-failure, unknown action), not the
service functions themselves (covered elsewhere).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestActionsRegistry:
    def test_known_actions_present(self):
        from runtime.executor import ACTIONS

        assert set(ACTIONS) == {"note", "todo", "agenda", "ask", "search", "import_markdown"}


class TestRunSteps:
    def test_all_steps_succeed(self):
        from runtime.executor import run_steps

        steps = [
            {"action": "note", "params": {"text": "hi"}},
            {"action": "search", "params": {"query": "q"}},
        ]
        with (
            patch("service.add_note", new=AsyncMock(return_value={"id": 1})),
            patch("service.search", new=AsyncMock(return_value={"documents": [], "memories": []})),
        ):
            results = asyncio.run(run_steps(steps))

        assert len(results) == 2
        assert all(r["status"] == "completed" for r in results)
        assert results[0]["output"] == {"id": 1}
        assert results[1]["output"] == {"documents": [], "memories": []}

    def test_stops_at_first_failure(self):
        from runtime.executor import run_steps

        steps = [
            {"action": "note", "params": {"text": "hi"}},
            {"action": "ask", "params": {"question": "?"}},
            {"action": "note", "params": {"text": "never reached"}},
        ]
        with (
            patch("service.add_note", new=AsyncMock(return_value={"id": 1})),
            patch("service.ask", new=AsyncMock(side_effect=RuntimeError("ollama down"))),
        ):
            results = asyncio.run(run_steps(steps))

        assert len(results) == 2  # third step never attempted
        assert results[0]["status"] == "completed"
        assert results[1]["status"] == "failed"
        assert "ollama down" in results[1]["error"]

    def test_unknown_action_fails_without_raising(self):
        from runtime.executor import run_steps

        steps = [{"action": "delete_everything", "params": {}}]
        results = asyncio.run(run_steps(steps))
        assert len(results) == 1
        assert results[0]["status"] == "failed"
        assert "Unknown action" in results[0]["error"]

    def test_empty_steps_returns_empty_results(self):
        from runtime.executor import run_steps

        assert asyncio.run(run_steps([])) == []

    def test_missing_required_param_fails_that_step(self):
        from runtime.executor import run_steps

        # "note" requires params.text — a step missing it should fail
        # gracefully (KeyError caught), not crash run_steps.
        steps = [{"action": "note", "params": {}}]
        results = asyncio.run(run_steps(steps))
        assert results[0]["status"] == "failed"
