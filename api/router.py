"""FlowCore API — FastAPI router.

SECURITY: This API binds to 127.0.0.1 only.  It is NOT accessible from
the network.  This is intentional — the API is for local Termux use only.

Endpoints (core):
  GET  /api/health         — health check
  GET  /api/status         — comprehensive runtime status (for web UI)

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

Endpoints (Chat / Web UI):
  POST /api/ask             — RAG ask via Ollama (see runtime/ollama.py)
  GET  /api/settings        — FlowCore version, platform, active Ollama endpoint/model

Endpoints (Sprint 15 — Flows):
  GET    /api/flows            — list flows
  POST   /api/flows            — create a flow ({name, steps})
  GET    /api/flows/{id}       — get a flow by id
  DELETE /api/flows/{id}       — delete a flow
  POST   /api/flows/{id}/run   — run a flow, returns the resulting execution
  GET    /api/executions           — list executions (optional ?flow_id=)
  GET    /api/executions/{id}      — get an execution by id
"""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from loguru import logger
from pydantic import BaseModel

import service

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


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
    kind: str = "note"  # "note" | "todo" | "agenda"


class AskRequest(BaseModel):
    question: str
    timeout: float | None = None


class FlowCreate(BaseModel):
    name: str
    steps: list[dict]


# ---------------------------------------------------------------------------
# In-memory store (lightweight version)
# ---------------------------------------------------------------------------

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
            result["capabilities"] = {cap: (adapter is not None) for cap, adapter in reg.list_capabilities().items()}
        except Exception:
            result["capabilities"] = {}

        # Doctor (quick run)
        try:
            from doctor.service import DoctorService

            report = DoctorService().run(verbose=False)
            result["doctor"] = [
                {"name": c.name, "status": c.status.value, "message": c.message, "fix": c.fix} for c in report.checks
            ]
        except Exception:
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
                ["termux-notification", "--id", str(data.id), "--title", data.title, "--content", data.body],
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
                            "total": parts[1],
                            "used": parts[2],
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

            results["documents"] = await DocumentRepository().search(q)
        except Exception:
            pass
        return results

    # ── Notes / todos / agenda (Sprint 12) ───────────────────────────────
    @app.get("/api/notes")
    async def list_notes(kind: str | None = Query(None)):
        try:
            return {"notes": await service.list_notes(kind=kind)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/notes", status_code=201)
    async def create_note(data: NoteCreate):
        try:
            result = await service.add_note(data.text, data.kind)
            logger.info("Note created via API: kind={} text={}", data.kind, data.text[:40])
            return result
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ── Passport (Sprint 12) ─────────────────────────────────────────────
    @app.get("/api/passport")
    async def get_passport(agent_name: str = Query("flowcore-ui"), ttl: int = Query(3600)):
        try:
            from passport.generator import PassportGenerator
            from passport.schema import AgentIdentity
            from passport.validator import PassportValidator

            gen = PassportGenerator(ttl=ttl)
            agent = AgentIdentity(name=agent_name, version=version)
            p = gen.issue(agent)

            # Validate what we just generated (hash integrity, not expired,
            # has agent identity, has capabilities) — exercises
            # PassportValidator for real instead of leaving it uncalled.
            validation = PassportValidator().validate(p)

            result = p.to_dict()
            result["validation"] = {"valid": validation.valid, "reason": validation.reason}
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ── Chat / Ask (Web UI) ──────────────────────────────────────────────
    @app.post("/api/ask")
    async def ask(data: AskRequest):
        from runtime.ollama import OllamaDiscoveryError, OllamaError

        try:
            answer, model = await service.ask(data.question, timeout=data.timeout)
        except OllamaDiscoveryError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except OllamaError as e:
            raise HTTPException(status_code=502, detail=str(e))

        return {"answer": answer, "model": model}

    # ── Settings (Web UI) ────────────────────────────────────────────────
    @app.get("/api/settings")
    async def get_settings():
        from runtime.ollama import discover_default_model, discover_ollama_endpoint, OllamaDiscoveryError

        ollama_info: dict = {"endpoint": None, "model": None, "error": None}
        try:
            ollama_info["endpoint"] = discover_ollama_endpoint()
        except OllamaDiscoveryError as e:
            ollama_info["error"] = str(e)

        if ollama_info["endpoint"]:
            try:
                ollama_info["model"] = discover_default_model()
            except OllamaDiscoveryError as e:
                ollama_info["error"] = str(e)

        return {
            "version": version,
            "platform": _platform,
            "ollama": ollama_info,
        }

    # ── Flows (Sprint 15) ────────────────────────────────────────────────
    @app.get("/api/flows")
    async def list_flows():
        return {"flows": await service.list_flows()}

    @app.post("/api/flows", status_code=201)
    async def create_flow(data: FlowCreate):
        try:
            return await service.create_flow(data.name, data.steps)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    @app.get("/api/flows/{flow_id}")
    async def get_flow(flow_id: int):
        try:
            return await service.get_flow(flow_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.delete("/api/flows/{flow_id}")
    async def delete_flow(flow_id: int):
        deleted = await service.delete_flow(flow_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Flow not found: {flow_id}")
        return {"deleted": True}

    @app.post("/api/flows/{flow_id}/run")
    async def run_flow(flow_id: int):
        try:
            return await service.run_flow(flow_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ── Executions (Sprint 15) ───────────────────────────────────────────
    @app.get("/api/executions")
    async def list_executions(flow_id: int | None = Query(None)):
        return {"executions": await service.list_executions(flow_id)}

    @app.get("/api/executions/{execution_id}")
    async def get_execution(execution_id: int):
        try:
            return await service.get_execution(execution_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    return app
