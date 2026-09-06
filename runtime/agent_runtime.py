"""Agent Runtime Engine managing execution lifecycle, retries, autonomy, and observability."""

from __future__ import annotations

import json
import time
import uuid
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime.events.schemas import Event
from runtime.events.bus import get_event_bus
from runtime.llm.model_router import get_model_router
from runtime.tools.registry import get_tool_registry
from runtime.memory.manager import get_memory_manager

STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage"
RUNS_FILE = STORAGE_DIR / "agent_runs.json"


class AgentRun:
    def __init__(
        self,
        agent_id: str,
        event_id: Optional[str] = None,
        autonomy_level: int = 1,
    ) -> None:
        self.run_id = f"run_{uuid.uuid4().hex[:12]}"
        self.agent_id = agent_id
        self.event_id = event_id
        self.autonomy_level = autonomy_level
        self.started_at = time.time()
        self.completed_at: Optional[float] = None
        self.status = "RUNNING"
        self.decision: Optional[str] = None
        self.tools_used: List[str] = []
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "event_id": self.event_id,
            "autonomy_level": self.autonomy_level,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "decision": self.decision,
            "tools_used": self.tools_used,
            "result": self.result,
            "error": self.error,
        }


class AgentRuntimeEngine:
    def __init__(self, runs_file: Path = RUNS_FILE) -> None:
        self.runs_file = runs_file
        self.runs_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.runs_file.exists():
            self._save_runs([])

    def _load_runs(self) -> List[Dict[str, Any]]:
        try:
            with open(self.runs_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_runs(self, runs: List[Dict[str, Any]]) -> None:
        with open(self.runs_file, "w", encoding="utf-8") as f:
            json.dump(runs, f, indent=2, ensure_ascii=False)

    def log_run(self, run: AgentRun) -> None:
        runs = self._load_runs()
        runs.append(run.to_dict())
        self._save_runs(runs)

    def list_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        raw = self._load_runs()
        return raw[-limit:]

    async def execute_agent_task(
        self,
        agent_id: str,
        task_prompt: str,
        event: Optional[Event] = None,
        autonomy_level: int = 1,
        max_retries: int = 2,
    ) -> AgentRun:
        run = AgentRun(agent_id=agent_id, event_id=event.id if event else None, autonomy_level=autonomy_level)
        tool_registry = get_tool_registry()
        memory_manager = get_memory_manager()
        router = get_model_router()

        attempt = 0
        success = False

        while attempt <= max_retries and not success:
            attempt += 1
            try:
                # Gather semantic context
                entity_id = event.entity if event else "default"
                semantic_facts = memory_manager.get_semantic_facts(entity_id)

                full_system_prompt = (
                    f"Você é o Agente Especializado '{agent_id}' no FlowCore (Investment Copilot).\n"
                    f"Nível de Autonomia: {autonomy_level}.\n"
                    f"Fatos de Contexto: {semantic_facts}\n"
                    "Raciocine passo a passo (OBSERVAR -> DETECTAR -> ENTENDER -> RACIOCINAR -> EXECUTAR)."
                )

                # LLM reasoning call via ModelRouter (DeepSeek default)
                response = router.generate(
                    prompt=task_prompt,
                    system_prompt=full_system_prompt,
                    agent_id=agent_id,
                )

                run.decision = response.get("content", "")
                run.status = "COMPLETED"
                run.completed_at = time.time()
                run.result = {"llm_response": response}

                # Record episode in memory
                memory_manager.add_episodic_event(
                    agent_id=agent_id,
                    client_id=entity_id,
                    event_summary=f"Execução com sucesso por {agent_id}",
                    details={"run_id": run.run_id, "decision": run.decision[:200]},
                )

                success = True

            except Exception as e:
                if attempt > max_retries:
                    run.status = "FAILED"
                    run.completed_at = time.time()
                    run.error = f"Failed after {attempt} attempts: {e}"
                else:
                    await asyncio.sleep(0.5 * attempt)  # Backoff

        self.log_run(run)
        return run


_engine_instance = AgentRuntimeEngine()

def get_agent_runtime() -> AgentRuntimeEngine:
    return _engine_instance
