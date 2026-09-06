"""Tests for Agent Runtime Engine."""

import pytest
from runtime.agent_runtime import get_agent_runtime, AgentRun
from runtime.events.schemas import Event

@pytest.mark.asyncio
async def test_agent_runtime_execution():
    runtime = get_agent_runtime()
    evt = Event(type="PORTFOLIO_OUT_OF_PROFILE", source="compliance", entity="cli_001", payload={"diff": 8.0})

    run = await runtime.execute_agent_task(
        agent_id="ComplianceAgent",
        task_prompt="Analise o desenquadramento do cliente cli_001",
        event=evt,
        autonomy_level=2,
    )

    assert run.status == "COMPLETED"
    assert run.decision is not None
    assert run.agent_id == "ComplianceAgent"

    runs = runtime.list_runs()
    assert len(runs) >= 1
