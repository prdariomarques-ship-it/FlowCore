"""FlowCore API — FastAPI router.

SECURITY: This API binds to 127.0.0.1 only.  It is NOT accessible from
the network.  This is intentional — the API is for local Termux use only.

Endpoints:
  GET  /api/health         — health check
  GET  /api/flows          — list flows
  POST /api/flows          — create a flow
  GET  /api/flows/{id}     — get a flow
  DELETE /api/flows/{id}   — delete a flow
  GET  /api/executions     — list executions
  POST /api/executions     — submit a task
  GET  /api/executions/{id}— get execution status
"""
from __future__ import annotations

import json
import time
import uuid

from fastapi import FastAPI, HTTPException, Query
from loguru import logger
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class FlowCreate(BaseModel):
    name: str
    config: dict | None = None


class FlowResponse(BaseModel):
    id: str
    name: str
    status: str
    created_at: float
    updated_at: float


class ExecutionSubmit(BaseModel):
    flow_id: str
    payload: dict | None = None


class ExecutionResponse(BaseModel):
    id: str
    flow_id: str
    status: str
    started_at: float | None = None
    finished_at: float | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float
    platform: dict


# ---------------------------------------------------------------------------
# In-memory store (replaces DB for the lightweight version)
# ---------------------------------------------------------------------------

_flows: dict[str, dict] = {}
_executions: dict[str, dict] = {}
_start_time = time.time()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def create_app(version: str = "0.1.0", platform_info: dict | None = None) -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(title="FlowCore API", version=version)
    _platform = platform_info or {}

    # ── Health ──────────────────────────────────────────────────────────
    @app.get("/api/health", response_model=HealthResponse)
    async def health():
        return HealthResponse(
            status="ok",
            version=version,
            uptime_seconds=time.time() - _start_time,
            platform=_platform,
        )

    # ── Flows ───────────────────────────────────────────────────────────
    @app.get("/api/flows")
    async def list_flows():
        return list(_flows.values())

    @app.post("/api/flows", response_model=FlowResponse)
    async def create_flow(data: FlowCreate):
        flow_id = uuid.uuid4().hex
        now = time.time()
        flow = {
            "id": flow_id,
            "name": data.name,
            "status": "created",
            "config": data.config,
            "created_at": now,
            "updated_at": now,
        }
        _flows[flow_id] = flow
        logger.info("Flow created: {} ({})", flow_id, data.name)
        return FlowResponse(**flow)

    @app.get("/api/flows/{flow_id}", response_model=FlowResponse)
    async def get_flow(flow_id: str):
        if flow_id not in _flows:
            raise HTTPException(status_code=404, detail="Flow not found")
        return FlowResponse(**_flows[flow_id])

    @app.delete("/api/flows/{flow_id}")
    async def delete_flow(flow_id: str):
        if flow_id not in _flows:
            raise HTTPException(status_code=404, detail="Flow not found")
        del _flows[flow_id]
        logger.info("Flow deleted: {}", flow_id)
        return {"deleted": flow_id}

    # ── Executions ──────────────────────────────────────────────────────
    @app.get("/api/executions")
    async def list_executions(flow_id: str | None = Query(None)):
        results = list(_executions.values())
        if flow_id:
            results = [e for e in results if e["flow_id"] == flow_id]
        return results

    @app.post("/api/executions", response_model=ExecutionResponse)
    async def submit_execution(data: ExecutionSubmit):
        if data.flow_id not in _flows:
            raise HTTPException(status_code=404, detail="Flow not found")
        exec_id = uuid.uuid4().hex
        now = time.time()
        execution = {
            "id": exec_id,
            "flow_id": data.flow_id,
            "status": "pending",
            "payload": data.payload,
            "started_at": None,
            "finished_at": None,
        }
        _executions[exec_id] = execution
        logger.info("Execution submitted: {} for flow {}", exec_id, data.flow_id)
        return ExecutionResponse(**execution)

    @app.get("/api/executions/{exec_id}", response_model=ExecutionResponse)
    async def get_execution(exec_id: str):
        if exec_id not in _executions:
            raise HTTPException(status_code=404, detail="Execution not found")
        return ExecutionResponse(**_executions[exec_id])

    return app
