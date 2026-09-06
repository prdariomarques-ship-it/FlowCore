"""API endpoints for Autonomous Agent Platform, Observability, Approvals, and Cost Tracking."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Body
from typing import Any, Dict, List, Optional

from runtime.events.schemas import Event, EventPriority, EventStatus
from runtime.events.bus import get_event_bus
from runtime.agent_runtime import get_agent_runtime
from runtime.approval.manager import get_approval_manager
from runtime.llm.cost_tracker import get_cost_tracker
from runtime.tools.registry import get_tool_registry

router = APIRouter(prefix="/api", tags=["Agentic Engine"])


@router.get("/agent-runs")
async def list_agent_runs(limit: int = 50) -> Dict[str, Any]:
    runtime = get_agent_runtime()
    runs = runtime.list_runs(limit=limit)
    return {"total": len(runs), "runs": runs}


@router.get("/ai-costs")
async def get_ai_costs() -> Dict[str, Any]:
    tracker = get_cost_tracker()
    return tracker.get_summary()


@router.get("/approvals")
async def list_approvals(pending_only: bool = False) -> Dict[str, Any]:
    mgr = get_approval_manager()
    items = mgr.list_pending_approvals() if pending_only else mgr.list_all_approvals()
    return {"total": len(items), "items": items}


@router.post("/approvals/{approval_id}/approve")
async def approve_request(approval_id: str, user: str = "advisor") -> Dict[str, Any]:
    mgr = get_approval_manager()
    try:
        res = mgr.resolve_approval(approval_id, approved=True, user=user)
        return {"status": "SUCCESS", "approval": res}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/approvals/{approval_id}/reject")
async def reject_request(approval_id: str, user: str = "advisor") -> Dict[str, Any]:
    mgr = get_approval_manager()
    try:
        res = mgr.resolve_approval(approval_id, approved=False, user=user)
        return {"status": "REJECTED", "approval": res}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/events")
async def publish_event(
    event_type: str = Body(..., embed=True),
    entity: str = Body("system", embed=True),
    payload: Dict[str, Any] = Body({}, embed=True),
    priority: str = Body("MEDIUM", embed=True),
) -> Dict[str, Any]:
    bus = get_event_bus()
    prio = EventPriority(priority.upper()) if priority.upper() in EventPriority.__members__ else EventPriority.MEDIUM
    evt = Event(
        type=event_type,
        source="api_trigger",
        entity=entity,
        payload=payload,
        priority=prio,
    )
    published = bus.publish(evt)
    return {"status": "PUBLISHED", "event": published}


@router.get("/tools")
async def list_tools() -> Dict[str, Any]:
    registry = get_tool_registry()
    tools = registry.list_tools()
    return {"total": len(tools), "tools": tools}
