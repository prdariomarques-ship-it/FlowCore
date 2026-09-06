"""FlowCore Agent Runner — passport-gated, persisted task execution.

Usage::

    runner = AgentRunner()
    runner.register(HealthAgent())
    record = runner.run_sync("health")
    print(record.status, record.result)
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger

from agents.base import BaseAgent, AgentRegistry
from agents.task_store import AgentTaskRecord, AgentTaskStore


class AgentRunner:
    """Run agents on demand, validate passport, persist results."""

    def __init__(
        self,
        store: AgentTaskStore | None = None,
        require_passport: bool = True,
    ) -> None:
        self._registry = AgentRegistry()
        self._store = store or AgentTaskStore()
        self._require_passport = require_passport
        self._auto_register_builtins()

    def register(self, agent: BaseAgent) -> None:
        self._registry.register(agent)

    def list_agents(self) -> list[dict[str, Any]]:
        return self._registry.list()

    def run_sync(
        self,
        agent_name: str,
        context: dict | None = None,
        passport_agent_name: str = "cli-agent",
    ) -> AgentTaskRecord:
        """Blocking wrapper for use from CLI / sync API code."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(
                        asyncio.run,
                        self.run(agent_name, context, passport_agent_name),
                    )
                    return future.result(timeout=60)
            return loop.run_until_complete(
                self.run(agent_name, context, passport_agent_name)
            )
        except RuntimeError:
            return asyncio.run(self.run(agent_name, context, passport_agent_name))

    async def run(
        self,
        agent_name: str,
        context: dict | None = None,
        passport_agent_name: str = "cli-agent",
    ) -> AgentTaskRecord:
        """Issue passport → validate → run agent → persist result."""
        record = AgentTaskRecord.new(agent_name, context)
        self._store.save(record)

        # Passport gate
        if self._require_passport:
            passport_error = self._check_passport(passport_agent_name)
            if passport_error:
                record.status = "failed"
                record.error = passport_error
                record.finished_at = time.time()
                self._store.save(record)
                logger.warning("Passport check failed for agent {}: {}", agent_name, passport_error)
                return record

        # Resolve agent
        agent = self._registry.get(agent_name)
        if agent is None:
            record.status = "failed"
            record.error = f"Agent '{agent_name}' not found. Available: {[a['name'] for a in self._registry.list()]}"
            record.finished_at = time.time()
            self._store.save(record)
            return record

        # Execute
        record.status = "running"
        record.started_at = time.time()
        self._store.save(record)

        try:
            result = await asyncio.wait_for(
                agent.run(context or {}),
                timeout=60.0,
            )
            record.status = "completed"
            record.result = result
            logger.info("Agent {} completed (task {})", agent_name, record.id)
        except asyncio.TimeoutError:
            record.status = "failed"
            record.error = "Timeout after 60s"
            logger.error("Agent {} timed out (task {})", agent_name, record.id)
        except Exception as exc:
            record.status = "failed"
            record.error = str(exc)
            logger.error("Agent {} failed: {}", agent_name, exc)

        record.finished_at = time.time()
        self._store.save(record)

        # Optional: Android notification
        self._maybe_notify(agent_name, record)

        return record

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _check_passport(self, agent_name: str) -> str | None:
        """Return error string if passport invalid, None if ok."""
        try:
            from passport.generator import PassportGenerator
            from passport.schema import AgentIdentity
            from passport.validator import PassportValidator
            gen = PassportGenerator(ttl=300)
            passport = gen.issue(AgentIdentity(name=agent_name))
            result = PassportValidator().validate(passport)
            if not result:
                return result.reason
            return None
        except Exception as exc:
            return f"passport error: {exc}"

    def _maybe_notify(self, agent_name: str, record: AgentTaskRecord) -> None:
        try:
            from runtime.shell import is_available, run
            if not is_available("termux-notification"):
                return
            emoji = "✅" if record.status == "completed" else "❌"
            body = f"{emoji} Agent {agent_name} {record.status}"
            if record.error:
                body += f": {record.error[:80]}"
            run(
                ["termux-notification", "--id", "9001",
                 "--title", "FlowCore Agent", "--content", body],
                timeout=5,
            )
        except Exception:
            pass

    def _auto_register_builtins(self) -> None:
        for cls_path in (
            ("agents.health_agent", "HealthAgent"),
            ("agents.doctor_agent", "DoctorAgent"),
            ("agents.market_close_agent", "MarketCloseAgent"),
            ("agents.daily_brief_agent", "DailyBriefAgent"),
            ("agents.notify_market_close_agent", "NotifyMarketCloseAgent"),
        ):
            try:
                mod = __import__(cls_path[0], fromlist=[cls_path[1]])
                self._registry.register(getattr(mod, cls_path[1])())
            except Exception:
                pass
