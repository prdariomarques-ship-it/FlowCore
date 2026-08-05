# FlowCore Architecture

This document describes what's actually built and wired together, as of Sprint 13. Where a component is real but unconnected, or where two components appear to overlap but don't, that's called out explicitly — this replaces an earlier, more aspirational version of this document that described several Sprint 8–11 components as planned or in-progress; most now exist, some differently shaped than originally sketched.

## Three entry points, one storage layer, no shared process

FlowCore is not one running process — it's three independent interfaces that each wrap the same underlying storage layer directly, with no communication between them:

```
┌──────────────┐   ┌──────────────────┐   ┌──────────────────────┐
│  CLI          │   │  FastAPI server   │   │  MCP stdio server     │
│  flowcore.py  │   │  (flowcore.py     │   │  (flowcore.py mcp →   │
│               │   │   serve → api/    │   │   mcp_server.py)      │
│               │   │   router.py)      │   │                       │
└──────┬───────┘   └────────┬─────────┘   └──────────┬────────────┘
       │                    │                          │
       └────────────────────┼──────────────────────────┘
                             ▼
                 ┌───────────────────────┐
                 │   Storage layer        │
                 │   DocumentRepository    │  ← SQLite (data/flowcore.db)
                 │   MemoryRepository       │  ← JSON (~/.flowcore/memories.json)
                 └───────────────────────┘
```

Each interface instantiates its own `DocumentRepository()`/`MemoryRepository()` independently and talks to the same on-disk files. That's the entire integration between them — no shared in-memory state, no HTTP calls between the FastAPI and MCP processes, no message bus. Some logic is duplicated as a result (e.g. the note-kind label mapping `{"note": "Nota", "todo": "TODO", "agenda": "Agenda"}` exists once in `api/router.py` and again, separately, in `mcp_server.py`'s note/todo/agenda tools). If unifying them is ever wanted, the two real options are: MCP calls the FastAPI endpoints over HTTP, or the shared logic gets extracted into a service layer both import. Neither exists today.

## The Ollama layer (`runtime/ollama.py`)

The one piece all three interfaces *do* share directly (not just via storage): `runtime/ollama.py`'s `discover_ollama_endpoint()`, `discover_default_model()`, and `generate()`. No fixed endpoint or model is assumed — endpoint/model resolution probes `127.0.0.1`, `host.docker.internal`, and the default network gateway (covering WSL2→Windows and Termux/LAN cases), and `generate()` handles warm-up, `/api/ps` polling, and a configurable timeout, raising one of four typed errors (`OllamaUnreachableError`, `OllamaModelNotInstalledError`, `OllamaSubscriptionRequiredError`, `OllamaModelLoadTimeoutError`) instead of a generic failure. `FLOWCORE_OLLAMA`/`FLOWCORE_MODEL` env vars always override auto-discovery when set.

```
flowcore.py (cmd_ask, cmd_ping, cmd_models, cmd_stats, cmd_doctor)  ─┐
mcp_server.py (flowcore_ask)                                        ├──> runtime/ollama.py ──> Ollama HTTP API
api/router.py (/api/ask)                                            ─┘
```

## Storage layer (`storage/`)

- `document_repo.py` — `DocumentRepository`, async, backed by SQLite via `aiosqlite` (`data/flowcore.db`). Has both native async methods (`insert`, `list_all`, `get_by_id`, `search`, `list_recent`, `count`, `count_by_source`) and `*_sync()` wrapper convenience methods that call `asyncio.run()` internally. **The `*_sync()` wrappers break when called from inside an already-running event loop** — this bit both `mcp_server.py` and `api/router.py` this sprint; both were fixed by awaiting the native async methods directly at the call site instead. The wrapper methods themselves are unchanged and would still break any future async caller that uses them.
- `memory_repo.py` — `MemoryRepository`, synchronous, backed by a JSON file (`~/.flowcore/memories.json`). No `asyncio.run()` involved, safe from any context.
- `database.py` — single source of truth for the SQLite path.

## Capability layer (`capability/`)

`CapabilityRegistry` + `Resolver` + per-platform adapters (`capability/adapters/{base,android,linux,termux}.py`). This is the "bridge" concept from earlier planning — capabilities like `getBattery()` resolve through the registry to whichever adapter is available on the current platform, so callers never reference `termux-battery-status` or platform-specific commands directly. Adapters share method names (`write_file`, `read_file`, `run_git`, ...) with real per-platform behavioral differences (e.g. Termux's `write_file` has richer `PermissionError` handling than Linux's) — this is intentional divergence, not copy-paste duplication.

## Passport (`passport/`)

`PassportGenerator` issues a signed (SHA-256 hash) runtime snapshot — agent identity, platform, capabilities, health, expiry — consumed by `GET /api/passport` and the Web UI's Sistema tab. `PassportValidator`/`ValidationResult` exist with full test coverage but currently have **no caller anywhere in the running application** — built ahead of a consumer that hasn't been wired up yet.

## Scheduling — two separate implementations, one actually used

- `runtime/job_scheduler.py`'s `JobScheduler` — backs the real `flowcore.py jobs` CLI command (list/add/remove/run). This is the one actually in use.
- `scheduler/service.py`'s `SchedulerService` (APScheduler wrapper) — only ever instantiated inside `cmd_selftest()`'s "is this importable" check. Not wired to anything else.

## Execution engine — built, not connected

`executor/engine.py`'s `ExecutorEngine` (async task queue with retry/timeout/concurrency limits) is, like `SchedulerService`, only ever instantiated inside `cmd_selftest()`. `api/router.py`'s `/api/flows` and `/api/executions` endpoints are a **pure in-memory dict stub** (`_flows`, `_executions`) — they do not call `ExecutorEngine` at all. A flow's `status` field is set once at creation and never transitions; an execution's `started_at`/`finished_at` are always `None` (a real gap flagged in `RELEASE_NOTES.md`, not fixed this sprint).

## Agents (`agents/`) — orphaned

`BaseAgent` (ABC) + `AgentRegistry` exist with a clean interface (`run()`, `health_check()`) but have **zero references anywhere else in the codebase**, confirmed by repo-wide grep. Reads as deliberate forward-looking scaffolding rather than an accidental leftover, but nothing currently instantiates or registers an agent.

## Doctor (`doctor/service.py`)

Health-check aggregator consumed by `flowcore.py doctor`, `GET /api/status`, and the Web UI's Caps tab. Includes four placeholder multi-provider bridge checks (`_check_qwen_bridge`, `_check_glm_bridge`, `_check_gemini_bridge`, `_check_claude_bridge`) that only verify an env var is set (`QWEN_PORT`, `GLM_HOST`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`) — no actual provider implementation exists behind any of them yet. `doctor/checks/` is an empty, unreferenced package, likely intended as a future home for splitting these checks out of `service.py`.

## Config (`config/`)

`config/loader.py` deep-merges `config/default.json` with an optional `config/local.json` (git-ignored, per-machine overrides — e.g. this dev machine's API port had to move off `8080` due to an unrelated Docker service), then applies `FLOWCORE__SECTION__KEY`-style environment variable overrides on top. Cached after first load (`get_config()`); `reload_config()` clears the cache.

## Web UI (`web/index.html`)

Single-file, single-page app (no build step, no framework) served by FastAPI's `GET /`. Seven tabs: Início (dashboard), Sistema (battery/storage/passport), Caps (capabilities + doctor), Memórias, Notas (notes/todo/agenda + global search), Chat (RAG via `/api/ask`), Config (`/api/settings`). Talks to the backend via relative-path `fetch()` calls (`const API=''`), so it's portable across whatever host/port FastAPI actually binds to.

## Runtime (`runtime/`)

Beyond `ollama.py` and `job_scheduler.py` above: `core.py` (`FlowCoreRuntime`, `detect_platform()`, SQLite init via SQLAlchemy — a *second*, separate database access path from `storage/document_repo.py`'s direct `aiosqlite` usage, intended for `flows`/`executions`/`settings` tables that currently back nothing, since `api/router.py`'s flows/executions are the in-memory stub described above), `daemon.py` (background heartbeat process), `kernel.py` (boot sequence, emits a Runtime Passport), `discovery.py`, `checkpoint.py`, `shell.py` (subprocess helpers used by the capability adapters).

## Security model

| Layer | Control |
|---|---|
| Network | FastAPI binds to `127.0.0.1` only — not network-exposed |
| Privilege | No root/sudo — user-space only |
| Secrets | Credentials via environment variables (`.env`), never hardcoded |
| Code | No `os.system()`, no shell injection (verified by `scripts/audit.py`) |

## What's genuinely tested vs. manually verified

136 automated tests (`tests/`) cover: capability adapters, checkpoint, daemon, doctor, passport, runtime discovery/kernel, scheduler. **The Ollama pipeline (`runtime/ollama.py`) and the Web UI have zero automated test coverage** — everything about them in this sprint was verified manually (live curl sweeps, a real headless-browser session, direct model benchmarking). The test suite itself has a known isolation bug: it writes real entries into the live `~/.flowcore/memories.json` rather than a temp store.

## Target platforms

| Platform | Status |
|---|---|
| Linux (WSL2, native) | Supported, primary dev target |
| Termux / Android | Supported |
| macOS | Untested this sprint, no known blockers |
| Windows (native) | Not a FlowCore runtime target — Ollama can run there and be reached from WSL2/Termux via `FLOWCORE_OLLAMA` |
| Docker | Not packaged |
