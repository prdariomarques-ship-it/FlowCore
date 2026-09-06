"""Tests for ComplianceAgent in agents/compliance_agent.py."""

import pytest
from agents.compliance_agent import ComplianceAgent


@pytest.mark.asyncio
async def test_compliance_agent_empty_run():
    agent = ComplianceAgent()
    res = await agent.run()
    assert res["status"] == "ok"
    assert "data" in res
    assert "total" in res["data"]
    assert "critical" in res["data"]
    assert "warnings" in res["data"]
    assert "items" in res["data"]


@pytest.mark.asyncio
async def test_compliance_agent_evaluates_violations():
    agent = ComplianceAgent()
    portfolio = {
        "id": "cliente-456",
        "name": "Maria Oliveira",
        "current_allocation": {
            "renda_variavel_brasil": 25.0,
            "renda_variavel_global": 15.0,
            "renda_fixa_brasil": 40.0,
        },
        "sleeve_limits": {
            "renda_variavel_max": 30.0,
            "renda_fixa_total_min": 55.0,
        },
    }

    res = await agent.run({"portfolio": portfolio})
    assert res["status"] == "ok"
    data = res["data"]
    assert data["total"] == 2
    assert data["critical"] == 2
    items = data["items"]

    rv_item = next((i for i in items if i["type"] == "EXCESSO_RV"), None)
    assert rv_item is not None
    assert rv_item["client_id"] == "cliente-456"
    assert rv_item["current"] == 40.0
    assert rv_item["limit"] == 30.0
    assert rv_item["diff"] == 10.0
    assert rv_item["severity"] == "CRITICAL"

    rf_item = next((i for i in items if i["type"] == "DEFICIT_RF"), None)
    assert rf_item is not None
    assert rf_item["current"] == 40.0
    assert rf_item["limit"] == 55.0
    assert rf_item["diff"] == 15.0
    assert rf_item["severity"] == "CRITICAL"


@pytest.mark.asyncio
async def test_compliance_agent_warning_threshold():
    agent = ComplianceAgent()
    portfolio = {
        "id": "cliente-789",
        "name": "Carlos Souza",
        "current_allocation": {
            "renda_variavel_brasil": 32.0,
            "renda_fixa_brasil": 68.0,
        },
        "sleeve_limits": {
            "renda_variavel_max": 30.0,
            "renda_fixa_total_min": 55.0,
        },
    }

    res = await agent.run({"portfolio": portfolio})
    data = res["data"]
    assert data["warnings"] == 1
    item = data["items"][0]
    assert item["type"] == "EXCESSO_RV"
    assert item["severity"] == "WARNING"
    assert item["diff"] == 2.0
