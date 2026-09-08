"""Tests for MarketCloseAgent and DailyBriefAgent — the real, useful agents
registered alongside health/doctor so "Agentes" in the dashboard runs actual
work instead of only trivial diagnostics.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestMarketCloseAgent:
    def test_name_and_description(self):
        from agents.market_close_agent import MarketCloseAgent
        a = MarketCloseAgent()
        assert a.name == "market_close"
        assert len(a.description) > 5

    def test_run_delegates_to_build_market_close(self):
        import asyncio
        from agents.market_close_agent import MarketCloseAgent

        with patch(
            "runtime.market_intelligence.market_close.build_market_close",
            return_value={"client_version": "x", "instagram_version": "y"},
        ):
            result = asyncio.run(MarketCloseAgent().run())

        assert result["status"] == "ok"
        assert result["data"]["client_version"] == "x"


class TestDailyBriefAgent:
    def test_name_and_description(self):
        from agents.daily_brief_agent import DailyBriefAgent
        a = DailyBriefAgent()
        assert a.name == "daily_brief"
        assert len(a.description) > 5

    def test_run_delegates_to_build_brief_without_llm_by_default(self):
        import asyncio
        from agents.daily_brief_agent import DailyBriefAgent

        with patch(
            "runtime.ai.brief_diario.build_brief", return_value={"telegram_text": "brief"}
        ) as mocked:
            result = asyncio.run(DailyBriefAgent().run())

        mocked.assert_called_once_with(use_llm=False)
        assert result["status"] == "ok"
        assert result["data"]["telegram_text"] == "brief"

    def test_run_respects_use_llm_context(self):
        import asyncio
        from agents.daily_brief_agent import DailyBriefAgent

        with patch("runtime.ai.brief_diario.build_brief", return_value={}) as mocked:
            asyncio.run(DailyBriefAgent().run({"use_llm": True}))

        mocked.assert_called_once_with(use_llm=True)


class TestNotifyMarketCloseAgent:
    def test_name_and_description(self):
        from agents.notify_market_close_agent import NotifyMarketCloseAgent
        a = NotifyMarketCloseAgent()
        assert a.name == "notify_market_close"
        assert len(a.description) > 5

    def test_sends_notification_with_latest_highlight(self, tmp_path):
        import asyncio
        from agents.notify_market_close_agent import NotifyMarketCloseAgent

        with patch.object(NotifyMarketCloseAgent, "_latest_highlight", return_value="Ibovespa +1,2%"):
            with patch("runtime.shell.is_available", return_value=True):
                with patch("runtime.shell.run") as mocked_run:
                    from runtime.shell import ShellResult
                    mocked_run.return_value = ShellResult(command=[], returncode=0, stdout="", stderr="")
                    result = asyncio.run(NotifyMarketCloseAgent().run())

        assert result["status"] == "ok"
        assert result["data"]["sent"] is True
        assert result["data"]["message"] == "Ibovespa +1,2%"

    def test_degrades_when_termux_notification_unavailable(self):
        import asyncio
        from agents.notify_market_close_agent import NotifyMarketCloseAgent

        with patch.object(NotifyMarketCloseAgent, "_latest_highlight", return_value=None):
            with patch("runtime.shell.is_available", return_value=False):
                result = asyncio.run(NotifyMarketCloseAgent().run())

        assert result["status"] == "ok"
        assert result["data"]["sent"] is False
        assert "disponível no FlowCore" in result["data"]["message"]

    def test_latest_highlight_reads_todays_saved_file(self, tmp_path):
        import json
        from datetime import UTC, datetime

        from agents.notify_market_close_agent import NotifyMarketCloseAgent

        date_key = datetime.now(UTC).strftime("%Y-%m-%d")
        (tmp_path / f"{date_key}.json").write_text(
            json.dumps({"raw_lines": ["DÓLAR: +0,3%", "outra linha"]})
        )
        with patch("agents.notify_market_close_agent._HISTORY_DIR", tmp_path):
            assert NotifyMarketCloseAgent()._latest_highlight() == "DÓLAR: +0,3%"

    def test_latest_highlight_none_when_no_file(self, tmp_path):
        from agents.notify_market_close_agent import NotifyMarketCloseAgent

        with patch("agents.notify_market_close_agent._HISTORY_DIR", tmp_path):
            assert NotifyMarketCloseAgent()._latest_highlight() is None


class TestRunnerRegistersNewAgents:
    def test_new_agents_are_registered(self, tmp_path):
        from agents.runner import AgentRunner
        from agents.task_store import AgentTaskStore

        runner = AgentRunner(store=AgentTaskStore(path=tmp_path / "history.json"), require_passport=False)
        names = [a["name"] for a in runner.list_agents()]
        assert "market_close" in names
        assert "daily_brief" in names
        assert "notify_market_close" in names
