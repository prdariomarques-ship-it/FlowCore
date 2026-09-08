"""FlowCore FlowRunner — executes flow steps in sequence via AgentRunner."""
from __future__ import annotations

import asyncio
import time

from loguru import logger

from flows.schema import Flow, FlowRun
from flows.store import FlowStore


class FlowRunner:
    """Execute a Flow: run each step's agent in order, persist the FlowRun."""

    def __init__(self, store: FlowStore | None = None) -> None:
        self._store = store or FlowStore()

    def run_sync(
        self,
        flow: Flow,
        context: dict | None = None,
    ) -> FlowRun:
        """Blocking wrapper — handles already-running event loops."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return pool.submit(
                        asyncio.run, self.run(flow, context)
                    ).result(timeout=300)
            return loop.run_until_complete(self.run(flow, context))
        except RuntimeError:
            return asyncio.run(self.run(flow, context))

    async def run(
        self,
        flow: Flow,
        context: dict | None = None,
    ) -> FlowRun:
        """Execute all steps, persist progress after each one."""
        from agents.runner import AgentRunner

        run = FlowRun.new(flow)
        self._store.save_run(run)

        if not flow.steps:
            run.status = "completed"
            run.started_at = time.time()
            run.finished_at = time.time()
            self._store.save_run(run)
            logger.info("Flow '{}' has no steps — completed immediately", flow.name)
            return run

        run.status = "running"
        run.started_at = time.time()
        self._store.save_run(run)

        # FlowRunner is an internal trusted orchestrator; passport not required
        agent_runner = AgentRunner(require_passport=False)

        try:
            for i, step in enumerate(flow.steps):
                step_ctx = {**(context or {}), **step.context}
                logger.info(
                    "Flow '{}' step {}/{}: running agent '{}'",
                    flow.name, i + 1, len(flow.steps), step.agent,
                )
                record = await agent_runner.run(
                    step.agent, step_ctx, passport_agent_name="flow-runner"
                )
                run.step_results.append({
                    "agent": step.agent,
                    "status": record.status,
                    "result": record.result,
                    "error": record.error,
                    "duration_seconds": record.duration_seconds,
                })
                self._store.save_run(run)

                if record.status == "failed":
                    run.status = "failed"
                    run.error = f"Step '{step.agent}' failed: {record.error}"
                    run.finished_at = time.time()
                    self._store.save_run(run)
                    logger.error("Flow '{}' failed at step '{}'", flow.name, step.agent)
                    return run

            run.status = "completed"
            logger.info("Flow '{}' completed ({} steps)", flow.name, len(flow.steps))
        except Exception as exc:
            run.status = "failed"
            run.error = str(exc)
            logger.error("Flow '{}' raised exception: {}", flow.name, exc)

        run.finished_at = time.time()
        self._store.save_run(run)
        return run
