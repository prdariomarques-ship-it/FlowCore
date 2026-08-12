"""FlowCore Service Layer.

Business logic shared by the CLI (flowcore.py), FastAPI (api/router.py),
and MCP (mcp_server.py) interfaces, so the same operation is never
implemented three times. Sprint 14, priority 1, task 2.

This layer never prints, never raises HTTPException, never formats an
MCP response — it returns plain values and lets LLMError/ValueError
propagate. Each interface catches what it needs and presents it in its
own idiom (CLI prints colored text, FastAPI maps to HTTP status codes,
MCP raises RuntimeError).
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from capability.registry import CapabilityRegistry
from runtime.agent import AgentEngine, ToolSpec
from runtime.exposure import ExposureEngine, compute_concentration
from runtime.decision import DecisionEngine
from runtime.impact import ImpactEngine
from runtime.llm import InMemoryMetrics, LLMRequest, LLMRouter, LocalFirstPolicy, ProviderRegistry
from runtime.llm.providers import OllamaProvider, OpenRouterProvider
from runtime.narrative import NarrativeEngine
from runtime.macro_score import MacroScoreEngine
from runtime.product_mapping import DEFAULT_SHELF, list_shelves, load_shelf, map_action
from runtime.regime import RegimeEngine
from storage import DocumentRepository, EventRepository, FlowRepository, MemoryRepository, PortfolioRepository

_doc_repo = DocumentRepository()
_mem_repo = MemoryRepository()
_flow_repo = FlowRepository()
_registry = CapabilityRegistry()
_event_repo = EventRepository()
_macro_score_engine = MacroScoreEngine(_event_repo)
_regime_engine = RegimeEngine(_macro_score_engine)
_portfolio_repo = PortfolioRepository()
_exposure_engine = ExposureEngine()
_impact_engine = ImpactEngine(_regime_engine)
_decision_engine = DecisionEngine(_impact_engine, _exposure_engine)
# LLM Router -- the single composition root for every LLM-backed
# feature. LocalFirstPolicy means cloud (OpenRouter) is only ever used
# when a caller explicitly opts in via request.metadata["allow_cloud"]
# -- see runtime/llm/policy.py. Ollama stays the always-on default,
# matching this project's existing "local-first" AI Philosophy.
_llm_registry = ProviderRegistry()
_llm_registry.register(OllamaProvider())
_llm_registry.register(OpenRouterProvider())
_llm_router = LLMRouter(_llm_registry, LocalFirstPolicy(), metrics=InMemoryMetrics())
_narrative_engine = NarrativeEngine(_llm_router)

# Canonical note/todo/agenda title labels. Previously CLI/MCP used
# "Note"/"TODO"/"Agenda" while api/router.py separately used
# "Nota"/"TODO"/"Agenda" for the same operation — picked one.
NOTE_KIND_LABELS = {"note": "Note", "todo": "TODO", "agenda": "Agenda"}


async def add_note(text: str, kind: str = "note") -> dict:
    """Create a note/todo/agenda document. Raises ValueError for an unknown kind."""
    if kind not in NOTE_KIND_LABELS:
        raise ValueError(f"kind must be one of {sorted(NOTE_KIND_LABELS)}, got {kind!r}")
    doc_id = await _doc_repo.insert(NOTE_KIND_LABELS[kind], text, kind)
    return {"id": doc_id, "kind": kind, "text": text}


async def list_notes(kind: str | None = None) -> list[dict]:
    """List note/todo/agenda documents, optionally filtered by kind."""
    docs = await _doc_repo.list_all()
    return [d for d in docs if d.get("source") in NOTE_KIND_LABELS and (kind is None or d.get("source") == kind)]


async def memory_save(text: str) -> dict:
    """Persist a memory. Thin wrapper so every caller (Agent included)
    goes through the same repository api/router.py's /api/memories
    already uses, instead of touching MemoryRepository directly."""
    return _mem_repo.add(text)


async def memory_recall(query: str) -> list[dict]:
    """Search stored memories by text/topic — the read side memory_save
    didn't have a caller for until the Agent needed one."""
    return _mem_repo.search(query)


async def build_rag_context(limit: int = 5) -> str:
    """Build a prompt-ready context string from the N most recent documents.

    Degrades to no context (rather than failing the whole ask) if listing
    documents itself errors — grounding is a nice-to-have, not a hard
    requirement for the model to answer at all.
    """
    try:
        recent_docs = await _doc_repo.list_recent(limit)
    except Exception:
        recent_docs = []
    if not recent_docs:
        return ""
    context = "Context from documents:\n"
    for doc in recent_docs:
        context += f"\n[{doc['title']}]\n{doc['content'][:300]}\n"
    return context


async def ask(question: str, timeout: float | None = None) -> tuple[str, str]:
    """RAG-grounded ask: ground with recent documents, generate via the
    LLM Router. Returns (answer, model). Raises an LLMError subclass on
    failure (LLMAuthenticationError/LLMModelNotFoundError/LLMTimeoutError/
    LLMProviderUnavailableError/LLMAllProvidersFailedError/
    LLMBudgetExceededError) — callers decide how to present it.

    Migrated from a direct runtime.ollama call to the Router — this is
    now the second (after runtime/narrative/) LLM Router consumer. Never
    sets metadata["allow_cloud"], so Chat stays local-only by default
    exactly like before the migration; nothing about *behavior* changed,
    only *which exception family* callers must catch (flowcore.py's
    cmd_ask, api/router.py's /api/ask, mcp_server.py's flowcore_ask were
    all updated in the same change — see docs/LLM_ROUTER_ARCHITECTURE.md).
    """
    context = await build_rag_context(5)

    system_prompt = "You are a helpful AI assistant. Use the provided context to answer questions accurately."
    prompt = f"{system_prompt}\n\nContext:\n{context}\n\nQuestion: {question}\n\nAnswer:"

    request = LLMRequest(prompt=prompt, timeout=timeout, metadata={"purpose": "chat"})
    # generate() blocks (network I/O + warm-up polling); run off the event
    # loop thread so FastAPI/MCP stay responsive to other requests. Harmless
    # for the CLI's single-coroutine asyncio.run() too.
    response = await asyncio.to_thread(_llm_router.generate, request)
    return response.text, response.model


async def llm_status() -> dict:
    """Introspection for the LLM Router: registered providers, which are
    currently available, and per-provider call metrics."""
    return _llm_router.status()


async def search(query: str) -> dict:
    """Search both documents and memories for a query string."""
    return {
        "documents": await _doc_repo.search(query),
        "memories": _mem_repo.search(query),
    }


async def import_markdown(filepath: str) -> dict:
    """Import a Markdown file into the document store, extracting an H1 title if present.

    Raises FileNotFoundError if the file doesn't exist.
    """
    path = Path(filepath).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    content = path.read_text(encoding="utf-8")
    title = path.stem
    for line in content.split("\n"):
        if line.startswith("# "):
            title = line[2:].strip()
            break
    doc_id = await _doc_repo.insert(title, content, str(path))
    return {"id": doc_id, "title": title, "lines": len(content.split("\n")), "chars": len(content)}


# ── Flows ────────────────────────────────────────────────────────────────────
# A Flow is a named, persisted, ordered list of steps. Running it (an
# Execution) runs each step through runtime.executor.run_steps, which only
# ever calls the service functions above — never arbitrary code.


async def create_flow(name: str, steps: list[dict]) -> dict:
    """Create a Flow. Raises ValueError if any step's action isn't a known one."""
    from runtime.executor import ACTIONS

    for step in steps:
        action = step.get("action")
        if action not in ACTIONS:
            raise ValueError(f"Unknown flow action: {action!r} (known: {sorted(ACTIONS)})")
    flow_id = await _flow_repo.create_flow(name, steps)
    return {"id": flow_id, "name": name, "steps": steps}


async def list_flows() -> list[dict]:
    return await _flow_repo.list_flows()


async def get_flow(flow_id: int) -> dict:
    flow = await _flow_repo.get_flow(flow_id)
    if flow is None:
        raise ValueError(f"Flow not found: {flow_id}")
    return flow


async def delete_flow(flow_id: int) -> bool:
    return await _flow_repo.delete_flow(flow_id)


async def run_flow(flow_id: int) -> dict:
    """Run every step of a Flow in order, persisting real status/timestamps/
    per-step results as it goes. Raises ValueError if the Flow doesn't exist.
    """
    from runtime.executor import run_steps

    flow = await _flow_repo.get_flow(flow_id)
    if flow is None:
        raise ValueError(f"Flow not found: {flow_id}")

    execution_id = await _flow_repo.create_execution(flow_id, flow["name"])
    await _flow_repo.start_execution(execution_id)

    step_results = await run_steps(flow["steps"])
    all_completed = len(step_results) == len(flow["steps"]) and all(r["status"] == "completed" for r in step_results)
    status = "completed" if all_completed else "failed"
    error = next((r["error"] for r in step_results if r["status"] == "failed"), None)

    await _flow_repo.finish_execution(execution_id, status, step_results, error)
    return await _flow_repo.get_execution(execution_id)


async def list_executions(flow_id: int | None = None, limit: int | None = None) -> list[dict]:
    return await _flow_repo.list_executions(flow_id, limit)


async def get_execution(execution_id: int) -> dict:
    execution = await _flow_repo.get_execution(execution_id)
    if execution is None:
        raise ValueError(f"Execution not found: {execution_id}")
    return execution


# ── Android capabilities (Sprint 17, Milestone 1) ─────────────────────────────
# Thin wrappers over capability.registry.CapabilityRegistry — the one place
# CLI/FastAPI/MCP all resolve these through, instead of each interface
# duplicating termux-* shell calls ad hoc (which /api/system and /api/notify
# used to do before this milestone). Run off-thread like ask() does for its
# blocking call, so a slow subprocess never blocks the event loop.


async def get_battery() -> dict:
    return (await asyncio.to_thread(_registry.call, "getBattery")).to_dict()


async def get_wifi_info() -> dict:
    return (await asyncio.to_thread(_registry.call, "getNetworkInfo")).to_dict()


async def get_disk_usage(path: str = "/data") -> dict:
    return (await asyncio.to_thread(_registry.call, "getDiskUsage", path)).to_dict()


async def get_clipboard() -> dict:
    return (await asyncio.to_thread(_registry.call, "getClipboard")).to_dict()


async def set_clipboard(text: str) -> dict:
    return (await asyncio.to_thread(_registry.call, "setClipboard", text)).to_dict()


async def send_notification(title: str, message: str) -> dict:
    return (await asyncio.to_thread(_registry.call, "sendNotification", title, message)).to_dict()


async def list_installed_apps() -> dict:
    return (await asyncio.to_thread(_registry.call, "listInstalledApps")).to_dict()


async def get_android_info() -> dict:
    return (await asyncio.to_thread(_registry.call, "getAndroidInfo")).to_dict()


# ── Outlook (Sprint 17, Milestone 2) ──────────────────────────────────────────
# runtime.outlook is imported locally inside each function, not at module
# level — msal/requests are an optional (requirements-api.txt) dependency,
# and service.py is also used by the core-tier CLI. A top-level import here
# would break `flowcore.py note "..."` etc. on an install without the API
# extras, for a feature those callers never touch.

_outlook_auth_task: dict = {"status": "idle"}  # idle | pending | complete | failed


async def outlook_auth_start() -> dict:
    """Begin the device code flow. Returns the code/URL to show the user
    immediately; the blocking wait-for-authorization happens in the
    background — poll outlook_auth_status() to see when it completes.
    """
    from runtime.outlook import complete_device_flow, start_device_flow

    flow = await asyncio.to_thread(start_device_flow)
    _outlook_auth_task["status"] = "pending"
    _outlook_auth_task.pop("error", None)

    async def _complete():
        try:
            await asyncio.to_thread(complete_device_flow, flow)
            _outlook_auth_task["status"] = "complete"
        except Exception as e:
            _outlook_auth_task["status"] = "failed"
            _outlook_auth_task["error"] = str(e)

    asyncio.create_task(_complete())
    return {
        "user_code": flow["user_code"],
        "verification_uri": flow["verification_uri"],
        "expires_in": flow["expires_in"],
        "message": flow.get("message", ""),
    }


async def outlook_auth_status() -> dict:
    from runtime.outlook import is_authenticated

    authenticated = await asyncio.to_thread(is_authenticated)
    return {**_outlook_auth_task, "authenticated": authenticated}


async def outlook_messages(limit: int = 10) -> list[dict]:
    from runtime.outlook import list_messages

    return await asyncio.to_thread(list_messages, limit)


async def outlook_unread_count() -> int:
    from runtime.outlook import get_unread_count

    return await asyncio.to_thread(get_unread_count)


async def outlook_search(query: str, limit: int = 10) -> list[dict]:
    from runtime.outlook import search_messages

    return await asyncio.to_thread(search_messages, query, limit)


# ── Calendar (Sprint 17, Milestone 3) ─────────────────────────────────────────
# Shares the same auth session as Outlook (runtime.microsoft_graph) — no
# separate outlook_auth_start()-style calendar auth function; the existing
# one already covers both (see runtime/microsoft_graph.py's combined SCOPES).


async def calendar_today() -> list[dict]:
    from runtime.calendar import list_today

    return await asyncio.to_thread(list_today)


async def calendar_tomorrow() -> list[dict]:
    from runtime.calendar import list_tomorrow

    return await asyncio.to_thread(list_tomorrow)


async def calendar_week() -> list[dict]:
    from runtime.calendar import list_week

    return await asyncio.to_thread(list_week)


async def calendar_next() -> dict | None:
    from runtime.calendar import get_next

    return await asyncio.to_thread(get_next)


async def calendar_search(query: str, limit: int = 10) -> list[dict]:
    from runtime.calendar import search_events

    return await asyncio.to_thread(search_events, query, limit)


async def calendar_create(
    subject: str,
    start: str,
    end: str,
    timezone_: str = "UTC",
    description: str = "",
    location: str = "",
    attendees: list[str] | None = None,
) -> dict:
    from runtime.calendar import create_event

    return await asyncio.to_thread(create_event, subject, start, end, timezone_, description, location, attendees)


async def calendar_update(event_id: str, **fields) -> dict:
    from runtime.calendar import update_event

    return await asyncio.to_thread(update_event, event_id, **fields)


async def calendar_delete(event_id: str) -> None:
    from runtime.calendar import delete_event

    return await asyncio.to_thread(delete_event, event_id)


# ── WhatsApp (Sprint 17, Milestone 4) ─────────────────────────────────────────
# runtime.whatsapp is imported locally, same optional-dependency reasoning
# as Outlook/Calendar (requests is requirements-api.txt-only).


async def whatsapp_health() -> dict:
    from runtime.whatsapp import check_health

    return await asyncio.to_thread(check_health)


async def whatsapp_status() -> dict:
    from runtime.whatsapp import get_status

    return await asyncio.to_thread(get_status)


async def whatsapp_send(number: str, text: str) -> dict:
    from runtime.whatsapp import send_message

    return await asyncio.to_thread(send_message, number, text)


# ── Integration Dashboard (Sprint 17, Milestone 6) ────────────────────────────
# Live-probe only — no history/persistence. Every check below hits the real
# service fresh each time this is called; "checked_at" is when THIS call ran,
# not a synchronization log (none of these integrations keep one). Confirmed
# with the user before building rather than inventing a history table nobody
# asked for a mechanism to populate.


async def _outlook_guard() -> dict | None:
    """Shared not-configured/not-authenticated check for every Outlook/Calendar
    probe below — they all share one Microsoft Graph auth session. Returns a
    status dict if the caller should short-circuit, None if the caller should
    proceed with its own capability-specific probe."""
    from runtime.microsoft_graph import is_authenticated

    if not os.getenv("OUTLOOK_CLIENT_ID"):
        return {"status": "not_configured", "detail": "OUTLOOK_CLIENT_ID not set", "error": None}
    authed = await asyncio.to_thread(is_authenticated)
    if not authed:
        detail = "Configured, not authenticated yet — run `outlook auth`"
        return {"status": "not_authenticated", "detail": detail, "error": None}
    return None


async def _check_outlook() -> dict:
    """The shared auth session's own status — distinct from the Mailbox/Calendar
    capability-specific probes below."""
    guard = await _outlook_guard()
    if guard is not None:
        return guard
    return {"status": "ok", "detail": "Authenticated", "error": None}


async def _check_outlook_mailbox() -> dict:
    guard = await _outlook_guard()
    if guard is not None:
        return guard
    from runtime.outlook import OutlookError, get_unread_count

    try:
        count = await asyncio.to_thread(get_unread_count)
        return {"status": "ok", "detail": f"{count} unread", "error": None}
    except OutlookError as e:
        return {"status": "error", "detail": str(e), "error": str(e)}


async def _check_outlook_calendar() -> dict:
    guard = await _outlook_guard()
    if guard is not None:
        return guard
    from runtime.calendar import CalendarError, list_today

    try:
        events = await asyncio.to_thread(list_today)
        return {"status": "ok", "detail": f"{len(events)} events today", "error": None}
    except CalendarError as e:
        return {"status": "error", "detail": str(e), "error": str(e)}


async def _check_whatsapp() -> dict:
    from runtime.whatsapp import WhatsAppError, WhatsAppNotConfiguredError, check_health, get_status

    try:
        health = await asyncio.to_thread(check_health)
    except WhatsAppError as e:
        return {"status": "unreachable", "detail": str(e), "error": str(e)}
    version = health.get("version", "?")
    if not os.getenv("EVOLUTION_API_KEY") or not os.getenv("EVOLUTION_INSTANCE_NAME"):
        detail = f"Evolution API v{version} reachable, no instance configured"
        return {"status": "not_configured", "detail": detail, "error": None}
    try:
        status = await asyncio.to_thread(get_status)
    except WhatsAppNotConfiguredError:
        detail = f"Evolution API v{version} reachable, no instance configured"
        return {"status": "not_configured", "detail": detail, "error": None}
    except WhatsAppError as e:
        return {"status": "error", "detail": str(e), "error": str(e)}
    state = (status.get("instance") or {}).get("state", "unknown")
    ok = state == "open"
    detail = f"Evolution API v{version} — instance {state}"
    return {"status": "ok" if ok else "error", "detail": detail, "error": None if ok else detail}


async def _check_ollama() -> dict:
    from runtime.ollama import OllamaDiscoveryError, discover_default_model, discover_ollama_endpoint

    try:
        endpoint = await asyncio.to_thread(discover_ollama_endpoint)
        model = await asyncio.to_thread(discover_default_model)
    except OllamaDiscoveryError as e:
        return {"status": "unreachable", "detail": str(e), "error": str(e)}
    return {"status": "ok", "detail": f"{endpoint} — model {model}", "error": None}


async def _check_android() -> dict:
    """Availability only — never invoke a capability with side effects (sending
    a notification, reading clipboard) just to check status. registry.get()
    returns an adapter or None; that alone is the presence check."""
    caps = ["getBattery", "getClipboard", "sendNotification", "listInstalledApps", "getNetworkInfo"]
    available = [c for c in caps if _registry.get(c) is not None]
    if not available:
        detail = "No Android capabilities available on this platform"
        return {"status": "unreachable", "detail": detail, "error": None, "capabilities": []}
    if len(available) < len(caps):
        detail = f"{len(available)}/{len(caps)} available: {', '.join(available)}"
    else:
        detail = f"All {len(caps)} capabilities available"
    return {"status": "ok", "detail": detail, "error": None, "capabilities": available}


async def _check_mcp() -> dict:
    """If service.py can import mcp_server at all, the tool registry exists —
    no not-configured/unreachable states needed here, just ok."""
    import mcp_server

    tools = await mcp_server.mcp.list_tools()
    return {"status": "ok", "detail": f"{len(tools)} tools registered", "error": None}


_CLI_COMMANDS = [
    "serve",
    "mcp",
    "run",
    "health",
    "version",
    "selftest",
    "chat",
    "remember",
    "recall",
    "memories",
    "import",
    "docs",
    "show",
    "ping",
    "models",
    "stats",
    "doctor",
    "status",
    "boot",
    "install",
    "bootstrap",
    "repair",
    "demo",
    "search",
    "daily",
    "sync",
    "watch",
    "obsidian",
    "ask",
    "note",
    "todo",
    "agenda",
    "ui",
    "daemon",
    "jobs",
    "flow",
    "android",
    "outlook",
    "calendar",
    "whatsapp",
    "integrations",
    "telegram",
    "observer",
]


async def cli_status() -> dict:
    """Metadata, not a reachability check — flowcore.py's CLI is only ever
    invoked directly by the user, there's nothing to probe. Command list is
    a literal enumeration of flowcore.py main()'s subparsers, not runtime
    introspection (argparse doesn't expose that cleanly from outside main())."""
    from config.loader import get_config

    return {"version": get_config()["app"]["version"], "commands": list(_CLI_COMMANDS)}


async def integrations_status() -> list[dict]:
    checks = [
        ("Outlook Auth", _check_outlook),
        ("Outlook Mailbox", _check_outlook_mailbox),
        ("Outlook Calendar", _check_outlook_calendar),
        ("WhatsApp", _check_whatsapp),
        ("Ollama", _check_ollama),
        ("Android", _check_android),
        ("MCP", _check_mcp),
    ]

    async def _run(name: str, fn) -> dict:
        start = time.monotonic()
        try:
            result = await fn()
        except Exception as e:
            result = {"status": "error", "detail": str(e), "error": str(e)}
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        return {
            "name": name,
            "latency_ms": latency_ms,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            **result,
        }

    return list(await asyncio.gather(*(_run(name, fn) for name, fn in checks)))


# ── Telegram (Sprint 17, Milestone 4) ─────────────────────────────────────────
# Not wired into integrations_status() above — that function is being actively
# extended by a separate in-flight task (docs/JULES_TASKS_INTEGRATION_DASHBOARD.md,
# GitHub issue #4), and touching it here risks a merge collision. Adding a
# Telegram row to the dashboard is a natural, small follow-up once that work lands.


async def telegram_health() -> dict:
    from runtime.telegram import check_health

    return await asyncio.to_thread(check_health)


async def telegram_configuration() -> dict:
    from runtime.telegram import get_configuration

    return await asyncio.to_thread(get_configuration)


async def telegram_send(text: str, chat_id: str | None = None) -> dict:
    from runtime.telegram import send_message

    return await asyncio.to_thread(send_message, text, chat_id)


# ── SCPX Observer Framework (Sprint 18) ─────────────────────────────────────────
# The "Market Data" stage of the SCPX pipeline (FLOWCORE_CONSTITUTION.md,
# "SCPX Vision"). Observers only observe — normalized MarketEvents out, no
# interpretation/scoring/recommendations. See runtime/observers/.


async def observer_registry_info() -> list[dict]:
    from runtime.observers.registry import registry

    return [{"source": o.source, "category": o.category, "symbol": o.symbol} for o in registry.all()]


async def observer_events() -> list[dict]:
    from runtime.observers.scheduler import scheduler

    events = await scheduler.run_once()
    return [e.to_dict() for e in events]


async def observer_source_events(source: str) -> list[dict]:
    from runtime.observers.scheduler import scheduler

    events = await scheduler.run_source(source)
    return [e.to_dict() for e in events]


async def observer_health() -> dict:
    from runtime.observers.scheduler import scheduler

    events = await scheduler.run_source("vix")
    return events[0].to_dict()


# ── SCPX Macro Score Engine (Sprint 19) ─────────────────────────────────────────
# Deterministic, explainable per-dimension scores computed from persisted
# MarketEvents (see runtime/macro_score/). No LLM, no interpretation beyond
# arithmetic — decision engines belong to FlowCore, not a language model.


async def macro_score_dimensions() -> dict:
    """Static: which dimensions are scored and which sources feed each. No I/O."""
    from runtime.macro_score import DIMENSIONS

    return dict(DIMENSIONS)


async def macro_score_compute(dimension: str) -> dict:
    score = await _macro_score_engine.compute_score(dimension)
    return score.to_dict()


async def macro_score_compute_all() -> list[dict]:
    scores = await _macro_score_engine.compute_all()
    return [s.to_dict() for s in scores]


# ── SCPX Regime Engine (Sprint 20) ──────────────────────────────────────────────
# Fase 3 of the pipeline — deterministic threshold classification of Macro
# Score Engine's z-scores. No LLM, no fused "master regime" (see
# runtime/regime/engine.py for why).


async def regime_classify(dimension: str) -> dict:
    signal = await _regime_engine.classify(dimension)
    return signal.to_dict()


async def regime_classify_all() -> list[dict]:
    signals = await _regime_engine.classify_all()
    return [s.to_dict() for s in signals]


# ── Portfolio Domain (Sprint 21, Phase 1) ───────────────────────────────────────
# Manual CRUD only in this phase (confirmed with the user) — the `source`
# column already supports future import/broker/Open Finance paths without
# a schema change, but nothing beyond manual entry is built yet.


async def create_portfolio(name: str) -> dict:
    portfolio_id = await _portfolio_repo.create_portfolio(name)
    return await _portfolio_repo.get_portfolio(portfolio_id)


async def list_portfolios() -> list[dict]:
    return await _portfolio_repo.list_portfolios()


async def get_portfolio(portfolio_id: int) -> dict:
    portfolio = await _portfolio_repo.get_portfolio(portfolio_id)
    if portfolio is None:
        raise ValueError(f"Portfolio not found: {portfolio_id}")
    return portfolio


async def delete_portfolio(portfolio_id: int) -> bool:
    return await _portfolio_repo.delete_portfolio(portfolio_id)


async def _ensure_asset_enriched(symbol: str) -> None:
    """Best-effort auto-classification for a new symbol — never blocks
    adding a holding. An unknown/unreachable symbol just stays
    unclassified until manually tagged via tag_asset()."""
    existing = await _portfolio_repo.get_asset(symbol)
    if existing is not None:
        return
    from runtime.portfolio.asset_provider import AssetProviderError, fetch_asset_info

    try:
        info = await asyncio.to_thread(fetch_asset_info, symbol)
    except AssetProviderError:
        return
    await _portfolio_repo.upsert_asset(symbol, **info)


async def add_holding(
    portfolio_id: int, symbol: str, quantity: float, average_cost: float, currency: str = "USD"
) -> dict:
    """Raises ValueError if the portfolio doesn't exist."""
    portfolio = await _portfolio_repo.get_portfolio(portfolio_id)
    if portfolio is None:
        raise ValueError(f"Portfolio not found: {portfolio_id}")
    holding_id = await _portfolio_repo.create_holding(portfolio_id, symbol, quantity, average_cost, currency)
    await _ensure_asset_enriched(symbol)
    return await _portfolio_repo.get_holding(holding_id)


async def list_holdings(portfolio_id: int) -> list[dict]:
    """Raises ValueError if the portfolio doesn't exist. Each holding is
    enriched with a live market value (never persisted — recomputed every
    call) and its asset's classification, when available."""
    portfolio = await _portfolio_repo.get_portfolio(portfolio_id)
    if portfolio is None:
        raise ValueError(f"Portfolio not found: {portfolio_id}")
    holdings = await _portfolio_repo.list_holdings(portfolio_id)

    from runtime.portfolio.valuation import value_holdings

    valued = await asyncio.to_thread(value_holdings, holdings)
    enriched = []
    for holding in valued:
        asset = await _portfolio_repo.get_asset(holding["symbol"])
        enriched.append({**holding, "asset": asset})
    return enriched


async def update_holding(holding_id: int, quantity: float | None = None, average_cost: float | None = None) -> dict:
    """Raises ValueError if the holding doesn't exist."""
    holding = await _portfolio_repo.get_holding(holding_id)
    if holding is None:
        raise ValueError(f"Holding not found: {holding_id}")
    await _portfolio_repo.update_holding(holding_id, quantity=quantity, average_cost=average_cost)
    return await _portfolio_repo.get_holding(holding_id)


async def delete_holding(holding_id: int) -> bool:
    return await _portfolio_repo.delete_holding(holding_id)


async def portfolio_summary(portfolio_id: int) -> dict:
    """Simple sums over live-valued holdings — arithmetic, not analysis.
    Sector/geography/theme exposure breakdowns are Phase 2 (Portfolio
    Intelligence), not built here. Holdings whose live price couldn't be
    fetched are excluded from the totals but counted separately, rather
    than silently treated as zero."""
    holdings = await list_holdings(portfolio_id)
    valued = [h for h in holdings if h["market_value"] is not None]
    total_market_value = sum(h["market_value"] for h in valued)
    total_cost_basis = sum(h["cost_basis"] for h in valued)
    total_unrealized_gain = total_market_value - total_cost_basis
    total_unrealized_gain_pct = (total_unrealized_gain / total_cost_basis * 100) if total_cost_basis else None
    return {
        "portfolio_id": portfolio_id,
        "holding_count": len(holdings),
        "valued_holding_count": len(valued),
        "total_market_value": total_market_value,
        "total_cost_basis": total_cost_basis,
        "total_unrealized_gain": total_unrealized_gain,
        "total_unrealized_gain_pct": total_unrealized_gain_pct,
    }


async def get_asset(symbol: str) -> dict:
    asset = await _portfolio_repo.get_asset(symbol)
    if asset is None:
        raise ValueError(f"Asset not found: {symbol}")
    return asset


async def tag_asset(symbol: str, **attributes: Any) -> dict:
    """Manually set/override attributes on an asset — merges with existing
    attributes, never fabricated, never auto-fetched. Every key must be
    one of runtime.portfolio.attributes.ASSET_ATTRIBUTE_FIELDS (the single
    canonical schema every interface — API, CLI, MCP — derives from);
    raises ValueError on an unknown key rather than silently writing an
    orphan attribute nothing else can see."""
    from runtime.portfolio.attributes import ASSET_ATTRIBUTE_FIELDS

    unknown = set(attributes) - set(ASSET_ATTRIBUTE_FIELDS)
    if unknown:
        raise ValueError(f"Unknown asset attribute(s): {sorted(unknown)}. Known: {sorted(ASSET_ATTRIBUTE_FIELDS)}")
    attrs = {k: v for k, v in attributes.items() if v is not None}
    await _portfolio_repo.upsert_asset(symbol, attributes=attrs)
    return await _portfolio_repo.get_asset(symbol)


# ── SCPX Exposure Engine (Sprint 22, Phase 2) ───────────────────────────────────
# Deterministic, explainable weighted classification breakdowns — no LLM.
# Pure computation over list_holdings()'s already-enriched output, so
# there's nothing here that can fail from a network call.


async def portfolio_exposure(portfolio_id: int, dimension: str | None = None) -> dict:
    """Raises ValueError if the portfolio doesn't exist, ExposureError if
    `dimension` is given and unrecognized. With no dimension, returns the
    full report (the 5 hard classification columns)."""
    holdings = await list_holdings(portfolio_id)
    if dimension:
        return _exposure_engine.by_dimension(holdings, dimension).to_dict()
    full = _exposure_engine.full_report(holdings)
    return {dim: report.to_dict() for dim, report in full.items()}


async def portfolio_concentration(portfolio_id: int) -> dict:
    """Raises ValueError if the portfolio doesn't exist."""
    holdings = await list_holdings(portfolio_id)
    return compute_concentration(holdings).to_dict()


# ── SCPX Portfolio Impact Engine (Sprint 23, Phase 3) ───────────────────────────
# Translates the current macro regime (Regime Engine) into expected impact
# on a specific portfolio's actual holdings. Deterministic rules only, no
# LLM. See runtime/impact/ for the full rule set and reasoning.


async def portfolio_impact(portfolio_id: int) -> dict:
    """Raises ValueError if the portfolio doesn't exist."""
    holdings = await list_holdings(portfolio_id)
    report = await _impact_engine.compute(portfolio_id, holdings)
    return report.to_dict()


def _enrich_with_products(rec: dict, shelf: str) -> dict:
    return {**rec, "products": map_action(rec["action_key"], shelf)}


async def portfolio_recommendations(portfolio_id: int, shelf: str = DEFAULT_SHELF) -> dict:
    """Layer 3 (generic recommendations, from portfolio_impact()) + Layer
    4 (concrete products for `shelf`, runtime/product_mapping/) combined
    into one convenience view. portfolio_impact() itself never sees
    `shelf` or product data — the separation is structural, not just
    documentation. Raises ValueError if the portfolio doesn't exist,
    ProductMappingError if `shelf` is unknown."""
    report = await portfolio_impact(portfolio_id)
    load_shelf(shelf)  # validate even when there are zero recommendations to enrich
    return {
        "portfolio_id": report["portfolio_id"],
        "shelf": shelf,
        "recommendations": [_enrich_with_products(r, shelf) for r in report["recommendations"]],
        "opportunities": [_enrich_with_products(r, shelf) for r in report["opportunities"]],
        "computed_at": report["computed_at"],
    }


async def product_shelves() -> list[str]:
    return list_shelves()


# ── SCPX Decision Engine (Sprint 24, Layer 5) ───────────────────────────────────
# Transforms the generic recommendations from portfolio_recommendations() into
# an ordered, explainable decision queue. Deterministic, no LLM. See
# runtime/decision/ for the full rule set.


async def portfolio_decision(portfolio_id: int, shelf: str = DEFAULT_SHELF) -> dict:
    """Raises ValueError if the portfolio doesn't exist, ProductMappingError
    if `shelf` is unknown."""
    holdings = await list_holdings(portfolio_id)
    load_shelf(shelf)  # validate even when there will be zero decisions
    report = await _decision_engine.compute(portfolio_id, holdings, shelf)
    return report.to_dict()


async def portfolio_decision_queue(portfolio_id: int, shelf: str = DEFAULT_SHELF) -> list[dict]:
    report = await portfolio_decision(portfolio_id, shelf)
    return report["decisions"]


async def portfolio_score(portfolio_id: int) -> dict:
    report = await portfolio_decision(portfolio_id)
    return report["portfolio_score"]


async def portfolio_reason_chain(portfolio_id: int, decision_id: str = "", shelf: str = DEFAULT_SHELF) -> dict:
    """With `decision_id`, returns just that decision's reason chain
    (raises ValueError if no current decision has that id). Without it,
    returns every current decision's reason chain, keyed by id."""
    report = await portfolio_decision(portfolio_id, shelf)
    if decision_id:
        match = next((d for d in report["decisions"] if d["id"] == decision_id), None)
        if match is None:
            raise ValueError(f"Decision not found: {decision_id!r}")
        return {"portfolio_id": portfolio_id, "decision_id": decision_id, "reason_chain": match["reason_chain"]}
    return {
        "portfolio_id": portfolio_id,
        "reason_chains": {d["id"]: d["reason_chain"] for d in report["decisions"]},
    }


# ── SCPX Narrative Engine (Sprint 25) ────────────────────────────────────────
# The only layer allowed to call an LLM in the whole SCPX pipeline, and
# strictly as presentation over an already-computed DecisionReport. See
# runtime/narrative/ for the fallback discipline.


async def portfolio_narrative(portfolio_id: int, shelf: str = DEFAULT_SHELF, timeout: float | None = None) -> dict:
    """Raises ValueError if the portfolio doesn't exist, ProductMappingError
    if `shelf` is unknown. Never raises for LLM unavailability -- degrades
    to a deterministic fallback narrative instead (see NarrativeReport.source)."""
    report = await portfolio_decision(portfolio_id, shelf)
    narrative = await _narrative_engine.generate(portfolio_id, report, timeout)
    return narrative.to_dict()


# ── Agent Engine ──────────────────────────────────────────────────────────────
# Natural-language entrypoint: the LLM picks one of the tools below (or
# answers directly from RAG context), FlowCore executes the pick for
# real, and the LLM turns the real result into a natural-language answer.
# Every tool here reuses an existing service function or repository
# method -- the Agent adds no new capability, only a language interface
# onto ones that already existed as separate REST endpoints/CLI commands.


async def _doctor_tool() -> dict:
    from doctor.service import DoctorService

    report = await asyncio.to_thread(DoctorService().run, verbose=False)
    return report.to_dict()


async def _memory_save_tool(text: str) -> dict:
    return await memory_save(text)


async def _memory_recall_tool(query: str) -> dict:
    return {"query": query, "matches": await memory_recall(query)}


async def _note_save_tool(text: str, kind: str = "note") -> dict:
    return await add_note(text, kind)


async def _portfolio_summary_tool(portfolio_id: int | None = None) -> dict:
    """portfolio_id is optional from the LLM's point of view -- when
    omitted, resolved deterministically (never guessed by the LLM): the
    one existing portfolio if there's exactly one, otherwise a ValueError
    asking which one, which the Agent surfaces verbatim as a clarifying
    question instead of inventing a portfolio."""
    if portfolio_id is None:
        portfolios = await list_portfolios()
        if not portfolios:
            raise ValueError("Nenhuma carteira cadastrada ainda -- crie uma carteira antes de pedir um resumo.")
        if len(portfolios) > 1:
            names = ", ".join(f"{p['id']}:{p['name']}" for p in portfolios)
            raise ValueError(f"Existe mais de uma carteira ({names}) -- diga o ID ou o nome da carteira desejada.")
        portfolio_id = portfolios[0]["id"]
    return await portfolio_summary(portfolio_id)


_agent_tools = [
    ToolSpec(
        name="doctor",
        description="Executa o diagnostico real do sistema FlowCore (Android, Termux, Ollama, rede, etc.).",
        handler=_doctor_tool,
    ),
    ToolSpec(
        name="memory_save",
        description="Salva uma informacao persistente na memoria do usuario.",
        parameters={"text": "string, obrigatorio"},
        handler=_memory_save_tool,
    ),
    ToolSpec(
        name="memory_recall",
        description="Busca informacoes ja salvas na memoria do usuario por palavra-chave.",
        parameters={"query": "string, obrigatorio"},
        handler=_memory_recall_tool,
    ),
    ToolSpec(
        name="note_save",
        description="Cria uma nota, tarefa (todo) ou item de agenda.",
        parameters={
            "text": "string, obrigatorio",
            "kind": 'string, opcional: "note" | "todo" | "agenda", padrao "note"',
        },
        handler=_note_save_tool,
    ),
    ToolSpec(
        name="portfolio_summary",
        description="Consulta o resumo (valor total, custo, ganho) de uma carteira existente.",
        parameters={"portfolio_id": "int, opcional se so existir uma carteira cadastrada"},
        handler=_portfolio_summary_tool,
    ),
]

_agent_engine = AgentEngine(_llm_router, _agent_tools)


async def agent_ask(question: str, timeout: float | None = None) -> dict:
    """Same LLMRouter, same LLMError contract as ask() -- callers (CLI,
    FastAPI, MCP) catch LLMError exactly like they already did for ask().
    Superset of ask(): when no tool applies, the LLM answers directly
    from the same RAG context ask() would have used."""
    context = await build_rag_context(5)
    result = await _agent_engine.handle(question, context=context, timeout=timeout)
    return result.to_dict()
