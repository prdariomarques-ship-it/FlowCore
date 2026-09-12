"""Tests for agents/ask_agent.py -- the AskAgent that finally makes
api/dashboard_routes.py's `if "ask" in agents:` branch real (previously
dead code: no agent named "ask" was ever registered).

The key invariant under test is the tenant-safety filter: only market_*
tools and regime_signals reach the multi-office Chat IA. Everything
else in service.py's full tool catalog (memory_save, note_save,
portfolio_summary, ...) has no office_id at all and must never be
reachable from this agent.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.ask_agent import AskAgent, _is_tenant_safe  # noqa: E402


class TestTenantSafeToolFilter:
    def test_market_tools_are_safe(self):
        for name in (
            "market_correlation",
            "market_risk",
            "market_rebalance",
            "market_briefing",
            "market_yield_curve",
            "market_fx",
            "market_alerts",
            "market_news",
            "market_scores_history",
            "market_events",
        ):
            assert _is_tenant_safe(name), name

    def test_regime_signals_is_safe(self):
        assert _is_tenant_safe("regime_signals")

    def test_personal_tools_are_not_safe(self):
        # These have no office_id anywhere (service.py's _memory_save_tool
        # etc.) -- exposing them here would leak one office's memory/notes/
        # portfolio to another.
        for name in (
            "memory_save",
            "memory_recall",
            "note_save",
            "portfolio_summary",
            "portfolio_impact",
            "portfolio_exposure",
            "portfolio_recommendations",
            "doctor",
        ):
            assert not _is_tenant_safe(name), name


class TestAskAgentBuildsARestrictedEngine:
    def test_only_tenant_safe_tools_are_passed_to_the_engine(self):
        from runtime.agent.models import ToolSpec

        async def _h(**_kw):
            return {}

        fake_tools = [
            ToolSpec(name="market_correlation", description="", handler=_h),
            ToolSpec(name="regime_signals", description="", handler=_h),
            ToolSpec(name="memory_save", description="", handler=_h),
            ToolSpec(name="portfolio_summary", description="", handler=_h),
        ]

        captured = {}

        class _FakeEngine:
            def __init__(self, router, tools):
                captured["tools"] = tools

            async def handle(self, question, context="", timeout=None):
                raise AssertionError("not exercised in this test")

        with (
            patch("service._agent_tools", fake_tools),
            patch("service._llm_router", object()),
            patch("runtime.agent.engine.AgentEngine", _FakeEngine),
        ):
            from agents.ask_agent import _build_engine

            _build_engine()

        names = {t.name for t in captured["tools"]}
        assert names == {"market_correlation", "regime_signals"}


class TestAskAgentRun:
    def test_empty_question_is_an_error_without_calling_the_engine(self):
        import asyncio

        with patch("agents.ask_agent._build_engine") as mocked_build:
            result = asyncio.run(AskAgent().run({"question": "   "}))

        assert result["status"] == "error"
        mocked_build.assert_not_called()

    def test_successful_tool_call_returns_ok_with_the_answer(self):
        import asyncio
        from runtime.agent.models import AgentResult

        fake_engine = AsyncMock()
        fake_engine.handle.return_value = AgentResult(
            answer="Correlação de 0.42 entre ouro e dólar.",
            model="deepseek-chat",
            tool_used="market_correlation",
        )

        with patch("agents.ask_agent._build_engine", return_value=fake_engine):
            result = asyncio.run(AskAgent().run({"question": "correlação ouro x dólar"}))

        assert result["status"] == "ok"
        assert result["data"]["answer"] == "Correlação de 0.42 entre ouro e dólar."
        assert result["data"]["tool_used"] == "market_correlation"

    def test_engine_failure_degrades_to_an_error_result_not_an_exception(self):
        import asyncio
        from runtime.llm.models import LLMAllProvidersFailedError

        fake_engine = AsyncMock()
        fake_engine.handle.side_effect = LLMAllProvidersFailedError("no provider available")

        with patch("agents.ask_agent._build_engine", return_value=fake_engine):
            result = asyncio.run(AskAgent().run({"question": "oi"}))

        assert result["status"] == "error"
        assert "no provider available" in result["data"]["reason"]


class TestAskAgentIsRegistered:
    def test_registered_in_agent_runner(self):
        from agents.runner import AgentRunner

        runner = AgentRunner(require_passport=False)
        names = {a["name"] for a in runner.list_agents()}
        assert "ask" in names
