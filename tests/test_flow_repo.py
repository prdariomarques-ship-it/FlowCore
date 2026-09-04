"""Tests for storage.flow_repo — FlowRepository (flows + executions).

No pytest-asyncio dependency in this project — each test wraps its async
body in a single asyncio.run() call at the top level, the same convention
established for CLI/production code (see ARCHITECTURE.md's storage
layer section).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _repo(tmp_path: Path):
    from storage.flow_repo import FlowRepository

    return FlowRepository(db_path=str(tmp_path / "flows_test.db"))


class TestFlows:
    def test_create_and_get_flow(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            steps = [{"action": "note", "params": {"text": "hi"}}]
            flow_id = await repo.create_flow("My Flow", steps)
            return await repo.get_flow(flow_id), steps

        flow, steps = asyncio.run(scenario())
        assert flow is not None
        assert flow["name"] == "My Flow"
        assert flow["steps"] == steps

    def test_get_missing_flow_returns_none(self, tmp_path):
        async def scenario():
            return await _repo(tmp_path).get_flow(999)

        assert asyncio.run(scenario()) is None

    def test_list_flows_ordered_most_recent_first(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            first_id = await repo.create_flow("First", [])
            second_id = await repo.create_flow("Second", [])
            flows = await repo.list_flows()
            return first_id, second_id, flows

        first_id, second_id, flows = asyncio.run(scenario())
        ids = [f["id"] for f in flows]
        assert ids.index(second_id) < ids.index(first_id)

    def test_delete_flow(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            flow_id = await repo.create_flow("Doomed", [])
            deleted = await repo.delete_flow(flow_id)
            gone = await repo.get_flow(flow_id)
            return deleted, gone

        deleted, gone = asyncio.run(scenario())
        assert deleted is True
        assert gone is None

    def test_delete_missing_flow_returns_false(self, tmp_path):
        async def scenario():
            return await _repo(tmp_path).delete_flow(999)

        assert asyncio.run(scenario()) is False


class TestExecutions:
    def test_execution_lifecycle_sets_real_timestamps(self, tmp_path):
        # This is the exact bug the old (Sprint 14-removed) stub had: status
        # never transitioned and started_at/finished_at were always None.
        async def scenario():
            repo = _repo(tmp_path)
            flow_id = await repo.create_flow("Flow", [])
            execution_id = await repo.create_execution(flow_id, "Flow")

            pending = await repo.get_execution(execution_id)

            await repo.start_execution(execution_id)
            running = await repo.get_execution(execution_id)

            results = [{"action": "note", "status": "completed", "output": {"id": 1}}]
            await repo.finish_execution(execution_id, "completed", results)
            finished = await repo.get_execution(execution_id)

            return pending, running, finished, results

        pending, running, finished, results = asyncio.run(scenario())

        assert pending["status"] == "pending"
        assert pending["started_at"] is None
        assert pending["finished_at"] is None

        assert running["status"] == "running"
        assert running["started_at"] is not None
        assert running["finished_at"] is None

        assert finished["status"] == "completed"
        assert finished["finished_at"] is not None
        assert finished["step_results"] == results
        assert finished["error"] is None

    def test_finish_execution_with_error(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            flow_id = await repo.create_flow("Flow", [])
            execution_id = await repo.create_execution(flow_id, "Flow")
            await repo.start_execution(execution_id)
            results = [{"action": "ask", "status": "failed", "error": "boom"}]
            await repo.finish_execution(execution_id, "failed", results, error="boom")
            return await repo.get_execution(execution_id)

        execution = asyncio.run(scenario())
        assert execution["status"] == "failed"
        assert execution["error"] == "boom"

    def test_list_executions_filtered_by_flow_id(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            flow_a = await repo.create_flow("A", [])
            flow_b = await repo.create_flow("B", [])
            exec_a = await repo.create_execution(flow_a, "A")
            await repo.create_execution(flow_b, "B")
            only_a = await repo.list_executions(flow_id=flow_a)
            every = await repo.list_executions()
            return exec_a, only_a, every

        exec_a, only_a, every = asyncio.run(scenario())
        assert [e["id"] for e in only_a] == [exec_a]
        assert len(every) == 2

    def test_get_missing_execution_returns_none(self, tmp_path):
        async def scenario():
            return await _repo(tmp_path).get_execution(999)

        assert asyncio.run(scenario()) is None

    def test_list_executions_respects_limit(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            flow_id = await repo.create_flow("Flow", [])
            for _ in range(5):
                await repo.create_execution(flow_id, "Flow")
            unlimited = await repo.list_executions()
            limited = await repo.list_executions(limit=2)
            return unlimited, limited

        unlimited, limited = asyncio.run(scenario())
        assert len(unlimited) == 5
        assert len(limited) == 2
        # Still most-recent-first under a limit.
        assert limited[0]["id"] > limited[1]["id"]

    def test_list_executions_respects_limit_with_flow_id_filter(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            flow_id = await repo.create_flow("Flow", [])
            for _ in range(4):
                await repo.create_execution(flow_id, "Flow")
            return await repo.list_executions(flow_id=flow_id, limit=1)

        limited = asyncio.run(scenario())
        assert len(limited) == 1
