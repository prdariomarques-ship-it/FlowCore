"""FlowCore Observer Loop -- the OBSERVAR/DETECTAR step of the autonomous
Agent Runtime cycle (§1, §13). Runs on a schedule (see api/router.py's
wiring of scheduler.service.SchedulerService), completely independent of
any browser tab or HTTP request being open.

Three real, computable signals per office, each handed to CoreOrchestrator
as its own event type -- nothing here is invented; every signal traces to
data ComplianceAgent, AgentEventRepository, or the outreach audit log
already has:

  PORTFOLIO_OUT_OF_PROFILE  A CRITICAL violation against a real,
                            contactable client (never the office's own
                            reference policy). WARNING-severity
                            violations deliberately do NOT page the
                            advisor -- they still show up in the
                            dashboard's alert table, but paging for every
                            WARNING would make the channel worth
                            ignoring.
  PORTFOLIO_BACK_IN_PROFILE A client whose previously-open violation (a
                            "processed" PORTFOLIO_OUT_OF_PROFILE event
                            for them) is no longer in this cycle's
                            CRITICAL list -- the earlier event is marked
                            resolved and the advisor gets the good news.
  CLIENT_FOLLOWUP_OVERDUE   A violation that's been open
                            (AgentEventRepository.first_seen, by
                            dedup_key) for at least
                            FLOWCORE_FOLLOWUP_THRESHOLD_DAYS (default 3)
                            with no successful outreach recorded since
                            (runtime/client_outreach.outreach_history) --
                            handled at LEVEL 3 by CoreOrchestrator (drafts
                            and files an approval, never sends alone).

Deduplication (AgentEventRepository.has_recent_duplicate) means an
unchanged, ongoing situation is only published once per 24h window --
observing it again every cycle must not mean notifying again every
cycle.
"""

from __future__ import annotations

import os
import time
from typing import Any

from loguru import logger

_DEFAULT_FOLLOWUP_THRESHOLD_DAYS = 3


async def observe_and_dispatch(llm_router: Any | None = None) -> dict[str, Any]:
    """One full observation cycle across every office. Never raises --
    a single office's failure (e.g. a transient market-data error inside
    ComplianceAgent) is logged and skipped, never allowed to abort the
    cycle for every other office."""
    from agents.compliance_agent import ComplianceAgent
    from agents.events import AgentEvent
    from agents.orchestrator import CoreOrchestrator
    from runtime.client_outreach import outreach_history
    from storage.agent_event_repo import AgentEventRepository
    from storage.client_repo import ClientRepository
    from storage.tenant_repo import TenantRepository

    event_repo = AgentEventRepository()
    orchestrator = CoreOrchestrator(llm_router=llm_router)
    offices = await TenantRepository().list_offices()
    followup_threshold_seconds = (
        int(os.environ.get("FLOWCORE_FOLLOWUP_THRESHOLD_DAYS", str(_DEFAULT_FOLLOWUP_THRESHOLD_DAYS))) * 86400
    )

    summary = {
        "offices_checked": 0, "events_published": 0, "events_deduplicated": 0,
        "followups_flagged": 0, "recoveries_detected": 0, "errors": [],
    }

    for office in offices:
        office_id = office["id"]
        try:
            client_ids = {c["id"] for c in await ClientRepository().list_clients(office_id)}
            result = await ComplianceAgent().run({"office_id": office_id})
            violations = [
                v for v in result["data"]["violations"]
                if v["severity"] == "CRITICAL" and v["client_id"] in client_ids
            ]

            active_dedup_keys: set[str] = set()
            now = time.time()

            for v in violations:
                violation_event = AgentEvent(
                    type="PORTFOLIO_OUT_OF_PROFILE", source="compliance_agent",
                    entity={"kind": "client", "id": v["client_id"]},
                    payload={"message": v["message"], "violation": v}, priority="CRITICAL",
                )
                dedup_key = violation_event.dedup_key()
                active_dedup_keys.add(dedup_key)

                if await event_repo.has_recent_duplicate(office_id, dedup_key):
                    summary["events_deduplicated"] += 1
                else:
                    published = await event_repo.publish(office_id, violation_event)
                    await orchestrator.handle_event(office_id, published)
                    summary["events_published"] += 1

                first_seen = await event_repo.first_seen(office_id, dedup_key)
                if first_seen is not None and (now - first_seen) >= followup_threshold_seconds:
                    followed_up = any(
                        h["timestamp"] >= first_seen and any(r.get("status") == "sent" for r in h["results"].values())
                        for h in outreach_history(office_id, v["client_id"])
                    )
                    if not followed_up:
                        followup_event = AgentEvent(
                            type="CLIENT_FOLLOWUP_OVERDUE", source="observer_loop",
                            entity={"kind": "client", "id": v["client_id"]},
                            payload={"violations": [v], "days_open": int((now - first_seen) // 86400)},
                            priority="HIGH",
                        )
                        if await event_repo.has_recent_duplicate(office_id, followup_event.dedup_key()):
                            summary["events_deduplicated"] += 1
                        else:
                            published = await event_repo.publish(office_id, followup_event)
                            await orchestrator.handle_event(office_id, published)
                            summary["followups_flagged"] += 1

            # ── Recovery: a previously-open violation no longer active ──────
            open_events = await event_repo.list_events(
                office_id, status="processed", type="PORTFOLIO_OUT_OF_PROFILE", limit=200,
            )
            already_notified_clients: set[str] = set()
            for oe in open_events:
                if oe["dedup_key"] in active_dedup_keys:
                    continue
                await event_repo.mark_resolved(office_id, oe["id"])
                client_key = oe["entity"].get("id")
                if client_key in already_notified_clients:
                    continue
                already_notified_clients.add(client_key)
                recovered_event = AgentEvent(
                    type="PORTFOLIO_BACK_IN_PROFILE", source="observer_loop",
                    entity=oe["entity"], priority="MEDIUM",
                )
                published = await event_repo.publish(office_id, recovered_event)
                await orchestrator.handle_event(office_id, published)
                summary["recoveries_detected"] += 1

            summary["offices_checked"] += 1
        except Exception as exc:
            logger.error("observer_loop: office {} failed: {}", office_id, exc)
            summary["errors"].append({"office_id": office_id, "error": str(exc)})

    return summary
