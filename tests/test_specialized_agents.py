"""Tests for Specialized Agents."""

import pytest
from agents.specialized_agents import (
    OpportunityAgent,
    ClientIntelligenceAgent,
    MarketIntelligenceAgent,
    FollowUpAgent,
    CommunicationAgent,
)

@pytest.mark.asyncio
async def test_specialized_agents_execution():
    opp_agent = OpportunityAgent()
    res_opp = await opp_agent.run({"client_id": "cli_001"})
    assert res_opp["status"] == "ok"
    assert "analysis" in res_opp

    mkt_agent = MarketIntelligenceAgent()
    res_mkt = await mkt_agent.run({"market_event": "Selic mantida em 10.50%"})
    assert res_mkt["status"] == "ok"
    assert "market_impact" in res_mkt

    fu_agent = FollowUpAgent()
    res_fu = await fu_agent.run({"client_id": "cli_002", "days_inactive": 30})
    assert res_fu["status"] == "ok"
    assert res_fu["follow_up_draft"]["requires_human_approval"] is True
