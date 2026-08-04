"""FlowCore MCP tool definitions and handlers."""
from __future__ import annotations

import json
from typing import Any

from mcp.types import Tool, TextContent, CallToolResult

# ── Tool definitions ──────────────────────────────────────────────────────────

FLOWCORE_TOOLS: list[Tool] = [
    Tool(
        name="capability_list",
        description=(
            "List all runtime capabilities available on this FlowCore instance "
            "(e.g. runPython, runGit, httpRequest, getBattery)."
        ),
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="doctor_run",
        description=(
            "Run the FlowCore doctor service and return a health report with "
            "pass/fail/warn status for each system check."
        ),
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="passport_issue",
        description=(
            "Issue a signed FlowCore passport for the given agent. "
            "The passport encodes available capabilities, permissions, and "
            "an expiry timestamp with a SHA-256 integrity hash."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Logical name for the requesting agent.",
                    "default": "mcp-agent",
                },
                "ttl": {
                    "type": "integer",
                    "description": "Passport lifetime in seconds (default 3600).",
                    "default": 3600,
                },
                "requested_capabilities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Capabilities to request (empty = all available).",
                },
            },
            "required": [],
        },
    ),
    Tool(
        name="memory_list",
        description="List the most recent memories stored in FlowCore.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum memories to return (default 20, max 200).",
                    "default": 20,
                }
            },
            "required": [],
        },
    ),
    Tool(
        name="memory_save",
        description="Save a text memory to FlowCore persistent storage.",
        inputSchema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Memory text to store."}
            },
            "required": ["text"],
        },
    ),
    Tool(
        name="note_list",
        description="List notes, todos, or agenda items stored in FlowCore.",
        inputSchema={
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["note", "todo", "agenda"],
                    "description": "Filter by kind (omit for all).",
                }
            },
            "required": [],
        },
    ),
    Tool(
        name="note_create",
        description="Create a note, todo, or agenda item in FlowCore.",
        inputSchema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Note content."},
                "kind": {
                    "type": "string",
                    "enum": ["note", "todo", "agenda"],
                    "description": "Kind of note (default: note).",
                    "default": "note",
                },
            },
            "required": ["text"],
        },
    ),
    Tool(
        name="search",
        description="Search memories and documents in FlowCore.",
        inputSchema={
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Search query string."}
            },
            "required": ["q"],
        },
    ),
    Tool(
        name="daemon_status",
        description="Get the current status of the FlowCore background daemon.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
]

_TOOL_MAP: dict[str, Tool] = {t.name: t for t in FLOWCORE_TOOLS}


# ── Handlers ──────────────────────────────────────────────────────────────────

def _ok(data: Any) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(text=json.dumps(data, indent=2, default=str))],
        isError=False,
    )


def _err(msg: str) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(text=msg)],
        isError=True,
    )


def handle_capability_list(_args: dict) -> CallToolResult:
    try:
        from capability.registry import CapabilityRegistry
        reg = CapabilityRegistry()
        caps = {
            cap: (adapter is not None)
            for cap, adapter in reg.list_capabilities().items()
        }
        return _ok({"capabilities": caps})
    except Exception as exc:
        return _err(f"capability_list failed: {exc}")


def handle_doctor_run(_args: dict) -> CallToolResult:
    try:
        from doctor.service import DoctorService
        report = DoctorService().run(verbose=False)
        checks = [
            {
                "name": c.name,
                "status": c.status.value,
                "message": c.message,
                "fix": c.fix,
            }
            for c in report.checks
        ]
        summary = {
            "total": len(checks),
            "passed": sum(1 for c in report.checks if c.status.value == "pass"),
            "failed": sum(1 for c in report.checks if c.status.value == "fail"),
            "warnings": sum(1 for c in report.checks if c.status.value == "warn"),
        }
        return _ok({"summary": summary, "checks": checks})
    except Exception as exc:
        return _err(f"doctor_run failed: {exc}")


def handle_passport_issue(args: dict) -> CallToolResult:
    try:
        from passport.generator import PassportGenerator
        from passport.schema import AgentIdentity
        agent_name = args.get("agent_name", "mcp-agent")
        ttl = int(args.get("ttl", 3600))
        requested = args.get("requested_capabilities") or None
        gen = PassportGenerator(ttl=ttl)
        agent = AgentIdentity(name=agent_name)
        p = gen.issue(agent, requested_capabilities=requested)
        return _ok(p.to_dict())
    except Exception as exc:
        return _err(f"passport_issue failed: {exc}")


def handle_memory_list(args: dict) -> CallToolResult:
    try:
        from storage import MemoryRepository
        limit = min(int(args.get("limit", 20)), 200)
        mems = MemoryRepository().list_all()
        return _ok({"memories": mems[-limit:], "total": len(mems)})
    except Exception as exc:
        return _err(f"memory_list failed: {exc}")


def handle_memory_save(args: dict) -> CallToolResult:
    try:
        from storage import MemoryRepository
        text = args.get("text", "")
        if not text:
            return _err("text is required")
        mem = MemoryRepository().add(text)
        return _ok({"saved": True, "memory": mem})
    except Exception as exc:
        return _err(f"memory_save failed: {exc}")


def handle_note_list(args: dict) -> CallToolResult:
    try:
        from storage import DocumentRepository
        docs = DocumentRepository().list_all_sync()
        kind_filter = args.get("kind")
        kinds = {"note", "todo", "agenda"}
        notes = [
            d for d in docs
            if d.get("source") in kinds
            and (kind_filter is None or d.get("source") == kind_filter)
        ]
        return _ok({"notes": notes})
    except Exception as exc:
        return _err(f"note_list failed: {exc}")


def handle_note_create(args: dict) -> CallToolResult:
    try:
        from storage import DocumentRepository
        text = args.get("text", "")
        kind = args.get("kind", "note")
        if not text:
            return _err("text is required")
        if kind not in ("note", "todo", "agenda"):
            return _err("kind must be note, todo, or agenda")
        label = {"note": "Nota", "todo": "TODO", "agenda": "Agenda"}[kind]
        doc_id = DocumentRepository().insert_sync(label, text, kind)
        return _ok({"id": doc_id, "kind": kind, "text": text})
    except Exception as exc:
        return _err(f"note_create failed: {exc}")


def handle_search(args: dict) -> CallToolResult:
    try:
        q = args.get("q", "")
        if not q:
            return _err("q is required")
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
        return _ok(results)
    except Exception as exc:
        return _err(f"search failed: {exc}")


def handle_daemon_status(_args: dict) -> CallToolResult:
    try:
        from runtime.daemon import FlowCoreDaemon
        return _ok(FlowCoreDaemon().status())
    except Exception as exc:
        return _err(f"daemon_status failed: {exc}")


# ── Dispatch ──────────────────────────────────────────────────────────────────

_HANDLERS = {
    "capability_list": handle_capability_list,
    "doctor_run": handle_doctor_run,
    "passport_issue": handle_passport_issue,
    "memory_list": handle_memory_list,
    "memory_save": handle_memory_save,
    "note_list": handle_note_list,
    "note_create": handle_note_create,
    "search": handle_search,
    "daemon_status": handle_daemon_status,
}


def dispatch(name: str, args: dict) -> CallToolResult:
    handler = _HANDLERS.get(name)
    if handler is None:
        return _err(f"Unknown tool: {name}")
    return handler(args)
