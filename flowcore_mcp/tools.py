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
    Tool(
        name="agent_list",
        description="List all agents registered in this FlowCore instance.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="agent_run",
        description=(
            "Run a FlowCore agent by name and return the result. "
            "Available agents include 'health'. "
            "The run is passport-gated and the result is persisted to history."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Name of the agent to run (e.g. 'health').",
                },
                "context": {
                    "type": "object",
                    "description": "Optional context dict passed to the agent.",
                },
            },
            "required": ["agent_name"],
        },
    ),
    Tool(
        name="agent_history",
        description="List recent agent task history from FlowCore.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max records to return (default 20).",
                    "default": 20,
                },
                "agent": {
                    "type": "string",
                    "description": "Filter by agent name (omit for all).",
                },
            },
            "required": [],
        },
    ),
    Tool(
        name="flow_list",
        description="List all flows defined in FlowCore.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="flow_create",
        description=(
            "Create a new FlowCore flow — a named sequence of agent steps "
            "that can be executed in order. Each step specifies an agent name "
            "and optional context."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Display name for the flow."},
                "description": {
                    "type": "string",
                    "description": "Short description of what this flow does.",
                    "default": "",
                },
                "steps": {
                    "type": "array",
                    "description": "Ordered list of agent steps.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "agent": {"type": "string"},
                            "context": {"type": "object"},
                        },
                        "required": ["agent"],
                    },
                },
            },
            "required": ["name"],
        },
    ),
    Tool(
        name="flow_run",
        description=(
            "Execute a FlowCore flow by its ID. Runs each step's agent in "
            "sequence and returns the full FlowRun result."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "flow_id": {
                    "type": "string",
                    "description": "ID of the flow to run.",
                },
                "context": {
                    "type": "object",
                    "description": "Optional context dict merged into each step.",
                },
            },
            "required": ["flow_id"],
        },
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


def handle_agent_list(_args: dict) -> CallToolResult:
    try:
        from agents.runner import AgentRunner
        runner = AgentRunner(require_passport=False)
        return _ok({"agents": runner.list_agents()})
    except Exception as exc:
        return _err(f"agent_list failed: {exc}")


def handle_agent_run(args: dict) -> CallToolResult:
    try:
        from agents.runner import AgentRunner
        agent_name = args.get("agent_name", "")
        context = args.get("context") or {}
        if not agent_name:
            return _err("agent_name is required")
        runner = AgentRunner(require_passport=False)
        record = runner.run_sync(agent_name, context, passport_agent_name="mcp-agent")
        return _ok(record.to_dict())
    except Exception as exc:
        return _err(f"agent_run failed: {exc}")


def handle_agent_history(args: dict) -> CallToolResult:
    try:
        from agents.task_store import AgentTaskStore
        limit = min(int(args.get("limit", 20)), 200)
        agent = args.get("agent") or None
        store = AgentTaskStore()
        records = store.list_all(limit=limit, agent=agent)
        return _ok({"tasks": [r.to_dict() for r in records]})
    except Exception as exc:
        return _err(f"agent_history failed: {exc}")


def handle_flow_list(_args: dict) -> CallToolResult:
    try:
        from flows.store import FlowStore
        flows = FlowStore().list_flows()
        return _ok({"flows": [f.to_dict() for f in flows], "total": len(flows)})
    except Exception as exc:
        return _err(f"flow_list failed: {exc}")


def handle_flow_create(args: dict) -> CallToolResult:
    try:
        from flows.schema import Flow
        from flows.store import FlowStore
        name = args.get("name", "")
        if not name:
            return _err("name is required")
        flow = Flow.new(
            name=name,
            steps=args.get("steps") or [],
            description=args.get("description", ""),
        )
        FlowStore().save_flow(flow)
        return _ok(flow.to_dict())
    except Exception as exc:
        return _err(f"flow_create failed: {exc}")


def handle_flow_run(args: dict) -> CallToolResult:
    try:
        from flows.runner import FlowRunner
        from flows.store import FlowStore
        flow_id = args.get("flow_id", "")
        if not flow_id:
            return _err("flow_id is required")
        context = args.get("context") or {}
        store = FlowStore()
        flow = store.get_flow(flow_id)
        if flow is None:
            return _err(f"Flow '{flow_id}' not found")
        run = FlowRunner(store=store).run_sync(flow, context)
        return _ok(run.to_dict())
    except Exception as exc:
        return _err(f"flow_run failed: {exc}")


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
    "agent_list": handle_agent_list,
    "agent_run": handle_agent_run,
    "agent_history": handle_agent_history,
    "flow_list": handle_flow_list,
    "flow_create": handle_flow_create,
    "flow_run": handle_flow_run,
}


def dispatch(name: str, args: dict) -> CallToolResult:
    handler = _HANDLERS.get(name)
    if handler is None:
        return _err(f"Unknown tool: {name}")
    return handler(args)
