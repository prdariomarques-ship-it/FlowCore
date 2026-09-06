"""Unit tests for ComplianceAgent."""

import pytest
from agents.compliance_agent import ComplianceAgent


@pytest.mark.asyncio
async def test_compliance_agent_defaults():
    agent = ComplianceAgent()
    result = await agent.run()

    assert result["status"] == "ok"
    assert result["total"] > 0
    assert "critical" in result
    assert "warnings" in result
    assert len(result["items"]) == result["total"]


@pytest.mark.asyncio
async def test_compliance_agent_severity_thresholds():
    agent = ComplianceAgent()

    test_clients = [
        {
            "client_id": "c1",
            "client_name": "Warning Client",
            "allocations": {"renda_variavel": 32.0},
            "limits": {"renda_variavel": 30.0},  # +2 p.p. -> WARNING
        },
        {
            "client_id": "c2",
            "client_name": "Critical Client",
            "allocations": {"renda_variavel": 38.0},
            "limits": {"renda_variavel": 30.0},  # +8 p.p. -> CRITICAL
        },
        {
            "client_id": "c3",
            "client_name": "Balanced Client",
            "allocations": {"renda_variavel": 25.0},
            "limits": {"renda_variavel": 30.0},  # Compliant -> 0 violations
        },
    ]

    result = await agent.run({"clients": test_clients})

    assert result["total"] == 2
    assert result["critical"] == 1
    assert result["warnings"] == 1

    items = result["items"]
    warn_item = next(i for i in items if i["client_id"] == "c1")
    crit_item = next(i for i in items if i["client_id"] == "c2")

    assert warn_item["severity"] == "WARNING"
    assert warn_item["diff"] == 2.0

    assert crit_item["severity"] == "CRITICAL"
    assert crit_item["diff"] == 8.0
