"""Core Orchestrator Agent for FlowCore Agentic Platform."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from agents.base import BaseAgent
from runtime.events.schemas import Event, EventPriority, EventStatus
from runtime.events.bus import get_event_bus
from runtime.agent_runtime import get_agent_runtime


class CoreOrchestrator(BaseAgent):
    name = "core_orchestrator"
    description = "Coordenador central do FlowCore. Recebe eventos, classifica, prioriza e delega para agentes especializados."
    version = "2.0.0"

    EVENT_AGENT_MAPPING = {
        "PORTFOLIO_OUT_OF_PROFILE": "compliance_agent",
        "CLIENT_INACTIVE": "follow_up_agent",
        "LEAD_INACTIVE": "follow_up_agent",
        "NEW_LEAD": "client_intelligence_agent",
        "CLIENT_WITHDRAWAL": "opportunity_agent",
        "CLIENT_DEPOSIT": "opportunity_agent",
        "MARKET_EVENT": "market_intelligence_agent",
        "PREPARE_COMMUNICATION": "communication_agent",
    }

    async def process_event(self, event: Event) -> Dict[str, Any]:
        """Classify event, select target specialized agent, and trigger runtime execution."""
        event_bus = get_event_bus()
        runtime = get_agent_runtime()

        # Update event status to PROCESSING
        event_bus.update_event_status(event.id, EventStatus.PROCESSING)

        target_agent = self.EVENT_AGENT_MAPPING.get(event.type, "general_intelligence_agent")

        prompt = (
            f"Evento recebido: {event.type}\n"
            f"Entidade: {event.entity}\n"
            f"Fonte: {event.source}\n"
            f"Prioridade: {event.priority.value}\n"
            f"Dados de Carga (Payload): {event.payload}\n"
            f"Analise e determine as ações necessárias para o cliente {event.entity}."
        )

        run = await runtime.execute_agent_task(
            agent_id=target_agent,
            task_prompt=prompt,
            event=event,
            autonomy_level=2 if event.priority == EventPriority.CRITICAL else 1,
        )

        status = EventStatus.PROCESSED if run.status == "COMPLETED" else EventStatus.FAILED
        event_bus.update_event_status(event.id, status, metadata={"run_id": run.run_id, "agent": target_agent})

        return {
            "orchestrated": True,
            "event_id": event.id,
            "target_agent": target_agent,
            "run_id": run.run_id,
            "status": run.status,
            "decision": run.decision,
        }

    async def run(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Poll and orchestrate pending events."""
        event_bus = get_event_bus()
        pending = event_bus.get_pending_events()

        orchestrated_runs = []
        for event in pending:
            res = await self.process_event(event)
            orchestrated_runs.append(res)

        return {
            "status": "ok",
            "processed_count": len(orchestrated_runs),
            "runs": orchestrated_runs,
        }


_orchestrator_instance = CoreOrchestrator()

def get_orchestrator() -> CoreOrchestrator:
    return _orchestrator_instance
