"""FlowCore API — FastAPI router.

SECURITY: This API binds to 127.0.0.1 only.  It is NOT accessible from
the network.  This is intentional — the API is for local Termux use only.

Endpoints (core):
  GET  /api/health         — health check
  GET  /api/status         — comprehensive runtime status (for web UI)

Endpoints (Sprint 11 — Android UX):
  GET  /api/memories        — list memories
  POST /api/memories        — save a memory
  POST /api/notify          — send Android notification (via capability layer)
  POST /api/daemon/start    — start background daemon
  POST /api/daemon/stop     — stop background daemon
  GET  /api/daemon/status   — daemon state
  GET  /                    — serve web UI (index.html)

Endpoints (Sprint 12 — Passport + expanded UI):
  GET  /api/system          — battery, storage, wifi, uptime (Android system info)
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
  GET    /api/executions           — list executions (optional ?flow_id=&limit=)
  GET    /api/executions/{id}      — get an execution by id

Endpoints (Sprint 17, Milestone 1 — Android integration):
  GET  /api/clipboard       — read clipboard
  POST /api/clipboard       — set clipboard ({text})
  GET  /api/apps            — list installed apps (Termux/Android only)

Endpoints (Sprint 17, Milestone 2 — Outlook integration, read-only):
  POST /api/outlook/auth/start    — begin device code flow
  GET  /api/outlook/auth/status   — poll auth status
  GET  /api/outlook/messages      — latest messages (?limit=)
  GET  /api/outlook/unread        — unread count
  GET  /api/outlook/search        — search messages (?q=&limit=)

Endpoints (Sprint 17, Milestone 3 — Calendar):
  GET    /api/calendar/today        — today's events
  GET    /api/calendar/tomorrow     — tomorrow's events
  GET    /api/calendar/week         — this week's events
  GET    /api/calendar/next         — next upcoming event
  GET    /api/calendar/search       — search events (?q=&limit=)
  POST   /api/calendar              — create an event
  PUT    /api/calendar/{id}         — update an event (any subset of fields)
  DELETE /api/calendar/{id}         — delete an event
  (auth is shared with Outlook — see /api/outlook/auth/*)

Endpoints (Sprint 17, Milestone 4 — WhatsApp via Evolution API):
  GET  /api/whatsapp/health   — is the Evolution API server reachable
  GET  /api/whatsapp/status   — configured instance's connection state
  POST /api/whatsapp/send     — send a message ({number, text})

Endpoints (Sprint 17, Milestone 6 — Integration Dashboard; expanded, Issue #4):
  GET  /api/integrations/status   — live status for Outlook Auth/Mailbox/Calendar,
                                      WhatsApp, Ollama, Android, MCP, FastAPI, CLI
                                      (no history — probed fresh each call)
  GET  /api/cli/status            — CLI version + registered command list (static)

Endpoints (Sprint 17, Milestone 4 — Telegram, reuses the spcx-monitor bot):
  GET  /api/telegram/health   — verifies the bot token via Telegram's getMe
  GET  /api/telegram/config   — static check: are the env vars set at all
  POST /api/telegram/send     — send a message ({text, chat_id?})

Endpoints (Sprint 18 — SCPX Observer Framework, normalized MarketEvents):
  GET  /api/observer/registry         — registered observers (name/category/symbol), no fetch
  GET  /api/observer/events           — run every observer now, return MarketEvents
  GET  /api/observer/events/{source}  — run one observer by name (treasury, dollar, vix, oil, gold)
  GET  /api/observer/health           — live reachability probe (runs the vix observer)

Endpoints (Sprint 19 — SCPX Macro Score Engine, deterministic per-dimension scores):
  GET  /api/macro-score/dimensions          — dimension -> source mapping, no computation
  GET  /api/macro-score/scores              — every dimension's score, computed now
  GET  /api/macro-score/scores/{dimension}  — one dimension by name

Endpoints (Sprint 20 — SCPX Regime Engine, deterministic threshold classification):
  GET  /api/regime/signals             — every dimension's regime (elevated/depressed/neutral)
  GET  /api/regime/signals/{dimension}  — one dimension by name

Endpoints (Sprint 21, Phase 1 — Portfolio Domain, manual CRUD):
  POST   /api/portfolios                          — create a portfolio ({name})
  GET    /api/portfolios                          — list portfolios
  GET    /api/portfolios/{id}                     — get a portfolio by id
  DELETE /api/portfolios/{id}                     — delete a portfolio (cascades to its holdings)
  GET    /api/portfolios/{id}/summary             — total market value/cost basis/gain (live)
  POST   /api/portfolios/{id}/holdings            — add a holding ({symbol, quantity, average_cost, currency?})
  GET    /api/portfolios/{id}/holdings            — list holdings, live-valued + asset-classified
  PUT    /api/holdings/{id}                       — update quantity/average_cost
  DELETE /api/holdings/{id}                       — delete a holding
  GET    /api/assets/{symbol}                     — an asset's classification
  PUT    /api/assets/{symbol}/attributes          — manually tag an asset (theme, duration, ...)

Endpoints (Sprint 22, Phase 2 — Exposure Engine, weighted classification breakdowns):
  GET  /api/portfolios/{id}/exposure              — full report (asset_class/sector/industry/country/currency)
  GET  /api/portfolios/{id}/exposure/{dimension}  — one dimension (hard column or any canonical soft attribute)
  GET  /api/portfolios/{id}/concentration         — HHI + top-1/top-5 weight

Endpoints (Sprint 23, Phase 3 — Portfolio Impact Engine, macro regime -> portfolio):
  GET  /api/portfolios/{id}/impact                     — impact, drivers, risk score, generic recs (product-agnostic)
  GET  /api/portfolios/{id}/recommendations?shelf=...  — same recs, enriched with products for `shelf` (default us_etf)
  GET  /api/product-shelves                            — list available shelves (config/product_shelves/*.json)

Endpoints (Sprint 24, Layer 5 — Decision Engine, ordered/explainable decision queue):
  GET  /api/portfolios/{id}/decision?shelf=...        — full DecisionReport (queue, score, top risks/opportunities)
  GET  /api/portfolios/{id}/decision/queue?shelf=...  — just the ordered decisions list
  GET  /api/portfolios/{id}/decision/score            — just the Decision Readiness Score (no shelf/products involved)
  GET  /api/portfolios/{id}/reason-chain?decision=...  — one decision's reason chain, or all of them if omitted

Endpoints (Sprint 25, Narrative Engine — LLM as presentation layer only, never in decisions):
  GET  /api/portfolios/{id}/narrative?shelf=...  — DecisionReport as prose (falls back if LLM unavailable)

Endpoints (LLM Router — provider-agnostic LLM access, added after Sprint 25):
  GET  /api/llm/status  — registered providers, availability, per-provider call metrics
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from loguru import logger
from pydantic import BaseModel, create_model

import service
from runtime.portfolio.attributes import ASSET_ATTRIBUTE_FIELDS
from runtime.product_mapping import DEFAULT_SHELF, ProductMappingError

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


class NoteCreate(BaseModel):
    text: str
    kind: str = "note"  # "note" | "todo" | "agenda"


class AskRequest(BaseModel):
    question: str
    timeout: float | None = None


class FlowCreate(BaseModel):
    name: str
    steps: list[dict]


class ClipboardSet(BaseModel):
    text: str


class CalendarEventCreate(BaseModel):
    subject: str
    start: str
    end: str
    timezone: str = "UTC"
    description: str = ""
    location: str = ""
    attendees: list[str] = []


class CalendarEventUpdate(BaseModel):
    subject: str | None = None
    start: str | None = None
    end: str | None = None
    timezone: str | None = None
    description: str | None = None
    location: str | None = None
    attendees: list[str] | None = None


class WhatsAppSend(BaseModel):
    number: str
    text: str


class TelegramSend(BaseModel):
    text: str
    chat_id: str | None = None


class PortfolioCreate(BaseModel):
    name: str


class HoldingCreate(BaseModel):
    symbol: str
    quantity: float
    average_cost: float
    currency: str = "USD"


class HoldingUpdate(BaseModel):
    quantity: float | None = None
    average_cost: float | None = None


# Derived from the canonical schema (runtime/portfolio/attributes.py),
# not hand-listed — a new attribute added there appears here for free,
# with no separate edit. See service.tag_asset()'s validation, which
# reads from the same list.
AssetTagRequest = create_model(
    "AssetTagRequest",
    **{field: (str | None, None) for field in ASSET_ATTRIBUTE_FIELDS},
)


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
        result = await service.send_notification(data.title, data.body)
        if result.get("success"):
            logger.info("Notification sent: {}", data.body[:40])
            return {"sent": True}
        return {"sent": False, "reason": result.get("error") or result.get("reason")}

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

    # ── System info (Sprint 12; Sprint 17 — routed through the capability layer) ──
    @app.get("/api/system")
    async def system_info():
        info: dict = {"uptime_api": round(time.time() - _start_time, 1)}

        # Four independent capability calls, each a subprocess with its own
        # timeout — run concurrently so total latency is the slowest single
        # call, not their sum (this was sequential before and visibly slow).
        battery, storage, wifi, android_info = await asyncio.gather(
            service.get_battery(),
            service.get_disk_usage(),
            service.get_wifi_info(),
            service.get_android_info(),
        )

        # Battery — capability layer's normalized keys (level/status/health/...)
        # translated back to the shape this endpoint has always returned
        # (percentage/status/health/...), so the Web UI's existing renderSys()
        # keeps working unchanged.
        if battery.get("success"):
            d = battery["data"]
            info["battery"] = {
                "percentage": d.get("level"),
                "status": d.get("status"),
                "health": d.get("health"),
                "temperature": d.get("temperature"),
                "plugged": d.get("plugged"),
            }

        if storage.get("success"):
            info["storage"] = storage["data"]

        if wifi.get("success"):
            info["wifi"] = wifi["data"]

        if android_info.get("success") and android_info["data"].get("release"):
            info["android_version"] = android_info["data"]["release"]

        return info

    # ── Clipboard, installed apps (Sprint 17, Milestone 1) ────────────────
    @app.get("/api/clipboard")
    async def get_clipboard():
        result = await service.get_clipboard()
        if not result.get("success"):
            raise HTTPException(status_code=503, detail=result.get("error") or result.get("reason"))
        return result["data"]

    @app.post("/api/clipboard")
    async def set_clipboard(data: ClipboardSet):
        result = await service.set_clipboard(data.text)
        if not result.get("success"):
            raise HTTPException(status_code=503, detail=result.get("error") or result.get("reason"))
        return result["data"]

    @app.get("/api/apps")
    async def list_apps():
        result = await service.list_installed_apps()
        if not result.get("success"):
            raise HTTPException(status_code=503, detail=result.get("error") or result.get("reason"))
        return result["data"]

    # ── Outlook (Sprint 17, Milestone 2) ──────────────────────────────────
    @app.post("/api/outlook/auth/start")
    async def outlook_auth_start():
        from runtime.outlook import OutlookError, OutlookNotConfiguredError

        try:
            return await service.outlook_auth_start()
        except OutlookNotConfiguredError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except OutlookError as e:
            raise HTTPException(status_code=502, detail=str(e))

    @app.get("/api/outlook/auth/status")
    async def outlook_auth_status():
        return await service.outlook_auth_status()

    @app.get("/api/outlook/messages")
    async def outlook_messages(limit: int = Query(10, le=50)):
        from runtime.outlook import OutlookAuthRequiredError, OutlookError, OutlookNotConfiguredError

        try:
            return {"messages": await service.outlook_messages(limit)}
        except OutlookNotConfiguredError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except OutlookAuthRequiredError as e:
            raise HTTPException(status_code=401, detail=str(e))
        except OutlookError as e:
            raise HTTPException(status_code=502, detail=str(e))

    @app.get("/api/outlook/unread")
    async def outlook_unread():
        from runtime.outlook import OutlookAuthRequiredError, OutlookError, OutlookNotConfiguredError

        try:
            return {"unread": await service.outlook_unread_count()}
        except OutlookNotConfiguredError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except OutlookAuthRequiredError as e:
            raise HTTPException(status_code=401, detail=str(e))
        except OutlookError as e:
            raise HTTPException(status_code=502, detail=str(e))

    @app.get("/api/outlook/search")
    async def outlook_search(q: str = Query(..., min_length=1), limit: int = Query(10, le=50)):
        from runtime.outlook import OutlookAuthRequiredError, OutlookError, OutlookNotConfiguredError

        try:
            return {"messages": await service.outlook_search(q, limit)}
        except OutlookNotConfiguredError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except OutlookAuthRequiredError as e:
            raise HTTPException(status_code=401, detail=str(e))
        except OutlookError as e:
            raise HTTPException(status_code=502, detail=str(e))

    # ── Calendar (Sprint 17, Milestone 3) ─────────────────────────────────
    # Shares /api/outlook/auth/start + /auth/status — one combined-scope
    # session covers Outlook and Calendar, no separate calendar auth route.
    @app.get("/api/calendar/today")
    async def calendar_today():
        from runtime.calendar import CalendarAuthRequiredError, CalendarError, CalendarNotConfiguredError

        try:
            return {"events": await service.calendar_today()}
        except CalendarNotConfiguredError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except CalendarAuthRequiredError as e:
            raise HTTPException(status_code=401, detail=str(e))
        except CalendarError as e:
            raise HTTPException(status_code=502, detail=str(e))

    @app.get("/api/calendar/tomorrow")
    async def calendar_tomorrow():
        from runtime.calendar import CalendarAuthRequiredError, CalendarError, CalendarNotConfiguredError

        try:
            return {"events": await service.calendar_tomorrow()}
        except CalendarNotConfiguredError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except CalendarAuthRequiredError as e:
            raise HTTPException(status_code=401, detail=str(e))
        except CalendarError as e:
            raise HTTPException(status_code=502, detail=str(e))

    @app.get("/api/calendar/week")
    async def calendar_week():
        from runtime.calendar import CalendarAuthRequiredError, CalendarError, CalendarNotConfiguredError

        try:
            return {"events": await service.calendar_week()}
        except CalendarNotConfiguredError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except CalendarAuthRequiredError as e:
            raise HTTPException(status_code=401, detail=str(e))
        except CalendarError as e:
            raise HTTPException(status_code=502, detail=str(e))

    @app.get("/api/calendar/next")
    async def calendar_next():
        from runtime.calendar import CalendarAuthRequiredError, CalendarError, CalendarNotConfiguredError

        try:
            return {"event": await service.calendar_next()}
        except CalendarNotConfiguredError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except CalendarAuthRequiredError as e:
            raise HTTPException(status_code=401, detail=str(e))
        except CalendarError as e:
            raise HTTPException(status_code=502, detail=str(e))

    @app.get("/api/calendar/search")
    async def calendar_search(q: str = Query(..., min_length=1), limit: int = Query(10, le=50)):
        from runtime.calendar import CalendarAuthRequiredError, CalendarError, CalendarNotConfiguredError

        try:
            return {"events": await service.calendar_search(q, limit)}
        except CalendarNotConfiguredError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except CalendarAuthRequiredError as e:
            raise HTTPException(status_code=401, detail=str(e))
        except CalendarError as e:
            raise HTTPException(status_code=502, detail=str(e))

    @app.post("/api/calendar", status_code=201)
    async def calendar_create(data: CalendarEventCreate):
        from runtime.calendar import CalendarAuthRequiredError, CalendarError, CalendarNotConfiguredError

        try:
            return await service.calendar_create(
                data.subject, data.start, data.end, data.timezone, data.description, data.location, data.attendees
            )
        except CalendarNotConfiguredError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except CalendarAuthRequiredError as e:
            raise HTTPException(status_code=401, detail=str(e))
        except CalendarError as e:
            raise HTTPException(status_code=502, detail=str(e))

    @app.put("/api/calendar/{event_id}")
    async def calendar_update(event_id: str, data: CalendarEventUpdate):
        from runtime.calendar import CalendarAuthRequiredError, CalendarError, CalendarNotConfiguredError

        fields = data.model_dump(exclude_none=True)
        if "timezone" in fields:
            fields["timezone_"] = fields.pop("timezone")
        if not fields:
            raise HTTPException(status_code=422, detail="No fields to update")
        try:
            return await service.calendar_update(event_id, **fields)
        except CalendarNotConfiguredError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except CalendarAuthRequiredError as e:
            raise HTTPException(status_code=401, detail=str(e))
        except CalendarError as e:
            raise HTTPException(status_code=502, detail=str(e))

    @app.delete("/api/calendar/{event_id}")
    async def calendar_delete(event_id: str):
        from runtime.calendar import CalendarAuthRequiredError, CalendarError, CalendarNotConfiguredError

        try:
            await service.calendar_delete(event_id)
            return {"deleted": True}
        except CalendarNotConfiguredError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except CalendarAuthRequiredError as e:
            raise HTTPException(status_code=401, detail=str(e))
        except CalendarError as e:
            raise HTTPException(status_code=502, detail=str(e))

    # ── WhatsApp (Sprint 17, Milestone 4) ─────────────────────────────────
    @app.get("/api/whatsapp/health")
    async def whatsapp_health():
        from runtime.whatsapp import WhatsAppError

        try:
            return await service.whatsapp_health()
        except WhatsAppError as e:
            raise HTTPException(status_code=502, detail=str(e))

    @app.get("/api/whatsapp/status")
    async def whatsapp_status():
        from runtime.whatsapp import WhatsAppError, WhatsAppNotConfiguredError

        try:
            return await service.whatsapp_status()
        except WhatsAppNotConfiguredError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except WhatsAppError as e:
            raise HTTPException(status_code=502, detail=str(e))

    @app.post("/api/whatsapp/send")
    async def whatsapp_send(data: WhatsAppSend):
        from runtime.whatsapp import WhatsAppError, WhatsAppNotConfiguredError

        try:
            return await service.whatsapp_send(data.number, data.text)
        except WhatsAppNotConfiguredError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except WhatsAppError as e:
            raise HTTPException(status_code=502, detail=str(e))

    # ── Integration Dashboard (Sprint 17, Milestone 6) ────────────────────
    @app.get("/api/integrations/status")
    async def integrations_status():
        # FastAPI's own row isn't an external reachability probe — if this
        # endpoint responds at all, FastAPI is definitionally up. Appended
        # here directly rather than routed through service.py's aggregator.
        from datetime import UTC, datetime

        # Copy, don't mutate — service.integrations_status()'s return value
        # isn't ours to modify in place.
        results = list(await service.integrations_status())
        uptime = round(time.time() - _start_time, 1)
        checked_at = datetime.now(UTC).isoformat()
        results.append(
            {
                "name": "FastAPI",
                "status": "ok",
                "detail": f"v{version}, {len(app.routes)} routes, {uptime}s uptime",
                "error": None,
                "latency_ms": 0.0,
                "checked_at": checked_at,
            }
        )
        cli = await service.cli_status()
        results.append(
            {
                "name": "CLI",
                "status": "ok",
                "detail": f"v{cli['version']}, {len(cli['commands'])} commands",
                "error": None,
                "latency_ms": 0.0,  # static metadata, not a live probe — see service.cli_status()
                "checked_at": checked_at,
            }
        )
        return {"integrations": results}

    @app.get("/api/cli/status")
    async def cli_status():
        return await service.cli_status()

    # ── Telegram (Sprint 17, Milestone 4) ─────────────────────────────────
    @app.get("/api/telegram/health")
    async def telegram_health():
        from runtime.telegram import TelegramError, TelegramNotConfiguredError

        try:
            return await service.telegram_health()
        except TelegramNotConfiguredError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except TelegramError as e:
            raise HTTPException(status_code=502, detail=str(e))

    @app.get("/api/telegram/config")
    async def telegram_config():
        return await service.telegram_configuration()

    @app.post("/api/telegram/send")
    async def telegram_send(data: TelegramSend):
        from runtime.telegram import TelegramError, TelegramNotConfiguredError

        try:
            return await service.telegram_send(data.text, data.chat_id)
        except TelegramNotConfiguredError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except TelegramError as e:
            raise HTTPException(status_code=502, detail=str(e))

    # ── SCPX Observer Framework (Sprint 18) ────────────────────────────────
    # Fixed paths ("registry", "events", "health") must be declared before
    # the dynamic {source} route below, or FastAPI would match them as one.
    @app.get("/api/observer/registry")
    async def observer_registry():
        return {"observers": await service.observer_registry_info()}

    @app.get("/api/observer/events")
    async def observer_events():
        return {"events": await service.observer_events()}

    @app.get("/api/observer/health")
    async def observer_health():
        from runtime.observers.base import ObserverError

        try:
            return await service.observer_health()
        except ObserverError as e:
            raise HTTPException(status_code=502, detail=str(e))

    @app.get("/api/observer/events/{source}")
    async def observer_source_events(source: str):
        from runtime.observers.registry import registry
        from runtime.observers.base import ObserverError

        if source not in registry.names():
            raise HTTPException(status_code=404, detail=f"Unknown observer: {source!r}")
        try:
            return {"events": await service.observer_source_events(source)}
        except ObserverError as e:
            raise HTTPException(status_code=502, detail=str(e))

    # ── SCPX Macro Score Engine (Sprint 19) ────────────────────────────────
    # Deterministic, explainable per-dimension scores — no LLM. Core-tier:
    # unlike the Observer routes above, nothing here can 502 from a network
    # failure, since this only reads already-persisted history.
    @app.get("/api/macro-score/dimensions")
    async def macro_score_dimensions():
        return {"dimensions": await service.macro_score_dimensions()}

    @app.get("/api/macro-score/scores")
    async def macro_score_scores():
        return {"scores": await service.macro_score_compute_all()}

    @app.get("/api/macro-score/scores/{dimension}")
    async def macro_score_dimension(dimension: str):
        from runtime.macro_score import DIMENSIONS

        if dimension not in DIMENSIONS:
            raise HTTPException(status_code=404, detail=f"Unknown dimension: {dimension!r}")
        return await service.macro_score_compute(dimension)

    # ── SCPX Regime Engine (Sprint 20) ─────────────────────────────────────
    # Deterministic threshold classification of Macro Score Engine's
    # z-scores — same no-network, no-502 property as the routes above.
    @app.get("/api/regime/signals")
    async def regime_signals():
        return {"signals": await service.regime_classify_all()}

    @app.get("/api/regime/signals/{dimension}")
    async def regime_signal(dimension: str):
        from runtime.macro_score import DIMENSIONS

        if dimension not in DIMENSIONS:
            raise HTTPException(status_code=404, detail=f"Unknown dimension: {dimension!r}")
        return await service.regime_classify(dimension)

    # ── Portfolio Domain (Sprint 21, Phase 1) ───────────────────────────────
    # Manual CRUD only — confirmed with the user, see service.py's module
    # comment for the full rationale.
    @app.post("/api/portfolios", status_code=201)
    async def create_portfolio(data: PortfolioCreate):
        return await service.create_portfolio(data.name)

    @app.get("/api/portfolios")
    async def list_portfolios():
        return {"portfolios": await service.list_portfolios()}

    @app.get("/api/portfolios/{portfolio_id}")
    async def get_portfolio(portfolio_id: int):
        try:
            return await service.get_portfolio(portfolio_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.delete("/api/portfolios/{portfolio_id}")
    async def delete_portfolio(portfolio_id: int):
        deleted = await service.delete_portfolio(portfolio_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Portfolio not found: {portfolio_id}")
        return {"deleted": True}

    @app.get("/api/portfolios/{portfolio_id}/summary")
    async def portfolio_summary(portfolio_id: int):
        try:
            return await service.portfolio_summary(portfolio_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.post("/api/portfolios/{portfolio_id}/holdings", status_code=201)
    async def add_holding(portfolio_id: int, data: HoldingCreate):
        try:
            return await service.add_holding(portfolio_id, data.symbol, data.quantity, data.average_cost, data.currency)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/portfolios/{portfolio_id}/holdings")
    async def list_holdings(portfolio_id: int):
        try:
            return {"holdings": await service.list_holdings(portfolio_id)}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.put("/api/holdings/{holding_id}")
    async def update_holding(holding_id: int, data: HoldingUpdate):
        try:
            return await service.update_holding(holding_id, data.quantity, data.average_cost)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.delete("/api/holdings/{holding_id}")
    async def delete_holding(holding_id: int):
        deleted = await service.delete_holding(holding_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Holding not found: {holding_id}")
        return {"deleted": True}

    @app.get("/api/assets/{symbol}")
    async def get_asset(symbol: str):
        try:
            return await service.get_asset(symbol)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.put("/api/assets/{symbol}/attributes")
    async def tag_asset(symbol: str, data: AssetTagRequest):
        return await service.tag_asset(symbol, **data.model_dump())

    # ── SCPX Exposure Engine (Sprint 22, Phase 2) ──────────────────────────
    # Deterministic weighted classification breakdowns — no LLM, no network
    # (pure computation over list_holdings()'s already-enriched output).
    @app.get("/api/portfolios/{portfolio_id}/exposure")
    async def portfolio_exposure(portfolio_id: int):
        try:
            return await service.portfolio_exposure(portfolio_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/portfolios/{portfolio_id}/exposure/{dimension}")
    async def portfolio_exposure_dimension(portfolio_id: int, dimension: str):
        from runtime.exposure import ExposureError

        try:
            return await service.portfolio_exposure(portfolio_id, dimension)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ExposureError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/portfolios/{portfolio_id}/concentration")
    async def portfolio_concentration(portfolio_id: int):
        try:
            return await service.portfolio_concentration(portfolio_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/portfolios/{portfolio_id}/impact")
    async def portfolio_impact(portfolio_id: int):
        try:
            return await service.portfolio_impact(portfolio_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/portfolios/{portfolio_id}/recommendations")
    async def portfolio_recommendations(portfolio_id: int, shelf: str = DEFAULT_SHELF):
        try:
            return await service.portfolio_recommendations(portfolio_id, shelf)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ProductMappingError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/product-shelves")
    async def product_shelves():
        return {"shelves": await service.product_shelves()}

    @app.get("/api/portfolios/{portfolio_id}/decision")
    async def portfolio_decision(portfolio_id: int, shelf: str = DEFAULT_SHELF):
        try:
            return await service.portfolio_decision(portfolio_id, shelf)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ProductMappingError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/portfolios/{portfolio_id}/decision/queue")
    async def portfolio_decision_queue(portfolio_id: int, shelf: str = DEFAULT_SHELF):
        try:
            return {"decisions": await service.portfolio_decision_queue(portfolio_id, shelf)}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ProductMappingError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/portfolios/{portfolio_id}/decision/score")
    async def portfolio_score(portfolio_id: int):
        try:
            return await service.portfolio_score(portfolio_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/portfolios/{portfolio_id}/reason-chain")
    async def portfolio_reason_chain(portfolio_id: int, decision: str = "", shelf: str = DEFAULT_SHELF):
        try:
            return await service.portfolio_reason_chain(portfolio_id, decision, shelf)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ProductMappingError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/portfolios/{portfolio_id}/narrative")
    async def portfolio_narrative(portfolio_id: int, shelf: str = DEFAULT_SHELF):
        try:
            return await service.portfolio_narrative(portfolio_id, shelf)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ProductMappingError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/llm/status")
    async def llm_status():
        return await service.llm_status()

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
        from runtime.llm import LLMAuthenticationError, LLMError, LLMModelNotFoundError, LLMTimeoutError

        try:
            answer, model = await service.ask(data.question, timeout=data.timeout)
        except (LLMAuthenticationError, LLMModelNotFoundError, LLMTimeoutError) as e:
            # Reached the provider; generation itself failed for a specific reason.
            raise HTTPException(status_code=502, detail=str(e))
        except LLMError as e:
            # Provider unreachable / all providers failed / budget exceeded.
            raise HTTPException(status_code=503, detail=str(e))

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
    async def list_executions(flow_id: int | None = Query(None), limit: int | None = Query(None, le=500)):
        return {"executions": await service.list_executions(flow_id, limit)}

    @app.get("/api/executions/{execution_id}")
    async def get_execution(execution_id: int):
        try:
            return await service.get_execution(execution_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    return app
