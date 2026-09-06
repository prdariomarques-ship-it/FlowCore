"""FlowCore Observer Loop -- the OBSERVAR/DETECTAR step of the autonomous
Agent Runtime cycle (§1, §13). Runs on a schedule (see api/router.py's
wiring of scheduler.service.SchedulerService), completely independent of
any browser tab or HTTP request being open.

For each office: runs ComplianceAgent for real (the same agent the
dashboard's /api/alerts already calls), and for every CRITICAL violation
against a real, contactable client (never the office's own reference
policy -- see the is_client distinction in api/dashboard_routes.py's
/api/alerts and agents/priority_engine.py's by_client grouping), publishes
a PORTFOLIO_OUT_OF_PROFILE event and immediately hands it to
CoreOrchestrator.

WARNING-severity violations deliberately do NOT autonomously page the
advisor -- they still show up in the dashboard's alert table, but paging
someone for every WARNING would make the channel worth ignoring. Only
CRITICAL crosses the bar for an unattended notification.

Deduplication (AgentEventRepository.has_recent_duplicate) means an
unchanged, ongoing violation is only published once per 24h window --
observing it again every cycle must not mean notifying again every
cycle.
"""

from __future__ import annotations

from typing import Any

from loguru import logger


async def observe_and_dispatch(llm_router: Any | None = None) -> dict[str, Any]:
    """One full observation cycle across every office. Never raises --
    a single office's failure (e.g. a transient market-data error inside
    ComplianceAgent) is logged and skipped, never allowed to abort the
    cycle for every other office."""
    from agents.compliance_agent import ComplianceAgent
    from agents.events import AgentEvent
    from agents.orchestrator import CoreOrchestrator
    from storage.agent_event_repo import AgentEventRepository
    from storage.client_repo import ClientRepository
    from storage.tenant_repo import TenantRepository

    event_repo = AgentEventRepository()
    orchestrator = CoreOrchestrator(llm_router=llm_router)
    offices = await TenantRepository().list_offices()

    summary = {"offices_checked": 0, "events_published": 0, "events_deduplicated": 0, "errors": []}

    for office in offices:
        office_id = office["id"]
        try:
            client_ids = {c["id"] for c in await ClientRepository().list_clients(office_id)}
            result = await ComplianceAgent().run({"office_id": office_id})
            violations = [
                v for v in result["data"]["violations"]
                if v["severity"] == "CRITICAL" and v["client_id"] in client_ids
            ]
            for v in violations:
                event = AgentEvent(
                    type="PORTFOLIO_OUT_OF_PROFILE", source="compliance_agent",
                    entity={"kind": "client", "id": v["client_id"]},
                    payload={"message": v["message"], "violation": v}, priority="CRITICAL",
                )
                if await event_repo.has_recent_duplicate(office_id, event.dedup_key()):
                    summary["events_deduplicated"] += 1
                    continue
                published = await event_repo.publish(office_id, event)
                await orchestrator.handle_event(office_id, published)
                summary["events_published"] += 1
            summary["offices_checked"] += 1
        except Exception as exc:
            logger.error("observer_loop: office {} failed: {}", office_id, exc)
            summary["errors"].append({"office_id": office_id, "error": str(exc)})

    return summary
