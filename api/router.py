"""FlowCore API — FastAPI router.

SECURITY: This API binds to 127.0.0.1 only.  It is NOT accessible from
the network.  This is intentional — the API is for local Termux use only.

Endpoints (core):
  GET  /api/health         — health check
  GET  /api/status         — comprehensive runtime status (for web UI)
  GET  /api/flows          — list flows
  POST /api/flows          — create a flow
  GET  /api/flows/{id}     — get a flow
  DELETE /api/flows/{id}   — delete a flow
  GET  /api/executions     — list executions
  POST /api/executions     — submit a task
  GET  /api/executions/{id}— get execution status

Endpoints (Sprint 11 — Android UX):
  GET  /api/memories        — list memories
  POST /api/memories        — save a memory
  POST /api/notify          — send Android notification via termux-notification
  POST /api/daemon/start    — start background daemon
  POST /api/daemon/stop     — stop background daemon
  GET  /api/daemon/status   — daemon state
  GET  /                    — serve web UI (index.html)

Endpoints (Sprint 12 — Passport + expanded UI):
  GET  /api/system          — battery, storage, uptime (Android system info)
  GET  /api/search          — search memories + docs (?q=)
  GET  /api/notes           — list notes/todos/agenda items
  POST /api/notes           — create a note/todo/agenda item
  GET  /api/passport        — generate and return current system passport
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from loguru import logger
from pydantic import BaseModel

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"


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


class MemoryCreate(BaseModel):
    text: str


class NotifyRequest(BaseModel):
    title: str = "FlowCore"
    body: str
    id: int = 1


class NoteCreate(BaseModel):
    text: str
    kind: str = "note"   # "note" | "todo" | "agenda"


# ---------------------------------------------------------------------------
# In-memory store (lightweight version)
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

    # ── Web UI ──────────────────────────────────────────────────────────
    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def serve_ui():
        index = _WEB_DIR / "index.html"
        if not index.exists():
            return HTMLResponse("<h2>FlowCore UI not found — run from project root</h2>", 404)
        return HTMLResponse(index.read_text(encoding="utf-8"))

    # ── Health ──────────────────────────────────────────────────────────
    @app.get("/api/health", response_model=HealthResponse)
    async def health():
        return HealthResponse(
            status="ok",
            version=version,
            uptime_seconds=time.time() - _start_time,
            platform=_platform,
        )

    # ── Comprehensive status (for web UI) ───────────────────────────────
    @app.get("/api/status")
    async def status():
        result: dict = {
            "version": version,
            "uptime_seconds": round(time.time() - _start_time, 1),
            "platform": _platform,
            "daemon": {},
            "capabilities": {},
            "doctor": [],
            "memory_count": 0,
        }

        # Daemon state
        try:
            from runtime.daemon import FlowCoreDaemon
            d = FlowCoreDaemon()
            result["daemon"] = d.status()
        except Exception as e:
            result["daemon"] = {"running": False, "error": str(e)}

        # Capabilities
        try:
            from capability.registry import CapabilityRegistry
            reg = CapabilityRegistry()
            result["capabilities"] = {
                cap: (adapter is not None)
                for cap, adapter in reg.list_capabilities().items()
            }
        except Exception as e:
            result["capabilities"] = {}

        # Doctor (quick run)
        try:
            from doctor.service import DoctorService
            report = DoctorService().run(verbose=False)
            result["doctor"] = [
                {"name": c.name, "status": c.status.value, "message": c.message,
                 "fix": c.fix}
                for c in report.checks
            ]
        except Exception as e:
            result["doctor"] = []

        # Memory count
        try:
            from storage import MemoryRepository
            result["memory_count"] = MemoryRepository().count()
        except Exception:
            pass

        return result

    # ── Memories ────────────────────────────────────────────────────────
    @app.get("/api/memories")
    async def list_memories(limit: int = Query(50, le=200)):
        try:
            from storage import MemoryRepository
            mems = MemoryRepository().list_all()
            return {"memories": mems[-limit:]}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/memories", status_code=201)
    async def create_memory(data: MemoryCreate):
        try:
            from storage import MemoryRepository
            mem = MemoryRepository().add(data.text)
            logger.info("Memory saved via API: {}", data.text[:40])
            return {"memory": mem}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ── Notify ──────────────────────────────────────────────────────────
    @app.post("/api/notify")
    async def notify(data: NotifyRequest):
        try:
            from runtime.shell import is_available, run
            if not is_available("termux-notification"):
                logger.warning("termux-notification not available")
                return {"sent": False, "reason": "termux-notification not installed"}
            result = run(
                ["termux-notification",
                 "--id", str(data.id),
                 "--title", data.title,
                 "--content", data.body],
                timeout=8,
            )
            if result.success:
                logger.info("Notification sent: {}", data.body[:40])
                return {"sent": True}
            return {"sent": False, "reason": result.stderr}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ── Daemon control ───────────────────────────────────────────────────
    @app.post("/api/daemon/start")
    async def daemon_start(interval: int = Query(60)):
        try:
            from runtime.daemon import FlowCoreDaemon
            result = FlowCoreDaemon().start(interval=interval)
            if result.get("started"):
                msg = f"Daemon iniciado (pid={result['pid']})"
            else:
                msg = f"Daemon já está ativo (pid={result['pid']})"
            return {"message": msg, **result}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/daemon/stop")
    async def daemon_stop():
        try:
            from runtime.daemon import FlowCoreDaemon
            result = FlowCoreDaemon().stop()
            msg = "Daemon parado" if result.get("stopped") else result.get("note", "Não estava ativo")
            return {"message": msg, **result}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/daemon/status")
    async def daemon_status():
        try:
            from runtime.daemon import FlowCoreDaemon
            return FlowCoreDaemon().status()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ── System info (Sprint 12) ──────────────────────────────────────────
    @app.get("/api/system")
    async def system_info():
        info: dict = {"uptime_api": round(time.time() - _start_time, 1)}

        # Battery via termux-battery-status
        try:
            from runtime.shell import is_available, run
            if is_available("termux-battery-status"):
                r = run(["termux-battery-status"], timeout=5)
                if r.success and r.stdout:
                    import json as _json
                    info["battery"] = _json.loads(r.stdout)
        except Exception:
            pass

        # Storage via df
        try:
            from runtime.shell import run as _run
            r = _run(["df", "-h", "/data"], timeout=5)
            if r.success and r.stdout:
                lines = r.stdout.strip().splitlines()
                if len(lines) >= 2:
                    parts = lines[1].split()
                    if len(parts) >= 4:
                        info["storage"] = {
                            "total": parts[1], "used": parts[2],
                            "avail": parts[3],
                        }
        except Exception:
            pass

        # Android version
        try:
            from runtime.shell import run as _run
            r = _run(["getprop", "ro.build.version.release"], timeout=3)
            if r.success and r.stdout.strip():
                info["android_version"] = r.stdout.strip()
        except Exception:
            pass

        return info

    # ── Search (Sprint 12) ───────────────────────────────────────────────
    @app.get("/api/search")
    async def search(q: str = Query(..., min_length=1)):
        results: dict = {"query": q, "memories": [], "documents": []}
        try:
            from storage import MemoryRepository
            results["memories"] = MemoryRepository().search(q)
        except Exception:
            pass
        try:
            from storage import DocumentRepository
            results["documents"] = DocumentRepository().search_sync(q)
        except Exception:
            pass
        return results

    # ── Notes / todos / agenda (Sprint 12) ───────────────────────────────
    @app.get("/api/notes")
    async def list_notes(kind: str | None = Query(None)):
        try:
            from storage import DocumentRepository
            docs = DocumentRepository().list_all_sync()
            kinds = {"note", "todo", "agenda"}
            filtered = [
                d for d in docs
                if d.get("source") in kinds
                and (kind is None or d.get("source") == kind)
            ]
            return {"notes": filtered}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/notes", status_code=201)
    async def create_note(data: NoteCreate):
        if data.kind not in ("note", "todo", "agenda"):
            raise HTTPException(status_code=422, detail="kind must be note, todo or agenda")
        try:
            from storage import DocumentRepository
            label = {"note": "Nota", "todo": "TODO", "agenda": "Agenda"}[data.kind]
            doc_id = DocumentRepository().insert_sync(label, data.text, data.kind)
            logger.info("Note created via API: kind={} text={}", data.kind, data.text[:40])
            return {"id": doc_id, "kind": data.kind, "text": data.text}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ── Passport (Sprint 12) ─────────────────────────────────────────────
    @app.get("/api/passport")
    async def get_passport(agent_name: str = Query("flowcore-ui"),
                           ttl: int = Query(3600)):
        try:
            from passport.generator import PassportGenerator
            from passport.schema import AgentIdentity
            gen = PassportGenerator(ttl=ttl)
            agent = AgentIdentity(name=agent_name, version=version)
            p = gen.issue(agent)
            return p.to_dict()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

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
