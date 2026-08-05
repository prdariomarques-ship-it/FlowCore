# FlowCore Architecture

This document describes what's actually built and wired together, as of Sprint 15 ("Fluxos Inteligentes"). Where a component is real but unconnected, or where two components appear to overlap but don't, that's called out explicitly.

## Three entry points, one service layer, one storage layer, no shared process

FlowCore is not one running process — it's three independent interfaces (CLI, FastAPI, MCP) that each run in their own process. As of Sprint 14 they no longer talk to storage directly for any operation that has real business logic behind it — `service.py` is the shared layer both `api/router.py` and `mcp_server.py` call for note-taking, RAG/ask, search, and flows; `flowcore.py` calls it too:

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
                 │   service.py           │  ← add_note(), list_notes(), ask(),
                 │                        │    search(), import_markdown(),
                 │                        │    create_flow()/run_flow()/...
                 └───────────┬───────────┘
                             ▼
                 ┌───────────────────────┐
                 │   Storage layer        │
                 │   DocumentRepository    │  ← SQLite (data/flowcore.db)
                 │   FlowRepository         │  ← SQLite, same file (flows, executions)
                 │   MemoryRepository       │  ← JSON (~/.flowcore/memories.json)
                 └───────────────────────┘
```

`service.py` owns the note-kind label mapping (`{"note": "Note", "todo": "TODO", "agenda": "Agenda"}` — previously defined twice, differently, in `api/router.py` and `mcp_server.py`) and the RAG/ask flow (context building + Ollama generation), so that logic now exists in exactly one place. Sprint 15 extended this to `search` and `import_markdown` too (see the Flows section below). Simple read-only listing/stats calls (`flowcore_docs`, `flowcore_stats`, etc. in `mcp_server.py`; the CLI's `docs`/`show`/`stats`/`daily` commands) still go straight to `DocumentRepository`/`MemoryRepository` — there's no real logic to share there beyond a repository call, so routing them through `service.py` would just be an extra layer with no behavioral benefit. One inconsistency remains: `api/router.py` instantiates a fresh `MemoryRepository()`/`DocumentRepository()` inline per endpoint rather than reusing a module-level instance the way `flowcore.py` and `mcp_server.py` do — harmless (both repos are stateless, re-reading from disk each call) but worth normalizing if `api/router.py` is touched again.

## The Ollama layer (`runtime/ollama.py`)

The one piece all three interfaces *do* share directly (not just via storage): `runtime/ollama.py`'s `discover_ollama_endpoint()`, `discover_default_model()`, and `generate()`. No fixed endpoint or model is assumed — endpoint/model resolution probes `127.0.0.1`, `host.docker.internal`, and the default network gateway (covering WSL2→Windows and Termux/LAN cases), and `generate()` handles warm-up, `/api/ps` polling, and a configurable timeout, raising one of four typed errors (`OllamaUnreachableError`, `OllamaModelNotInstalledError`, `OllamaSubscriptionRequiredError`, `OllamaModelLoadTimeoutError`) instead of a generic failure. `FLOWCORE_OLLAMA`/`FLOWCORE_MODEL` env vars always override auto-discovery when set.

```
flowcore.py (cmd_ask, cmd_ping, cmd_models, cmd_stats, cmd_doctor)  ─┐
mcp_server.py (flowcore_ask)                                        ├──> runtime/ollama.py ──> Ollama HTTP API
api/router.py (/api/ask)                                            ─┘
```

## Storage layer (`storage/`)

- `document_repo.py` — `DocumentRepository`, async-only, backed by SQLite via `aiosqlite` (`data/flowcore.db`): `insert`, `list_all`, `get_by_id`, `search`, `list_recent`, `count`, `count_by_source`. Sprint 14 removed the `*_sync()` wrapper methods that used to call `asyncio.run()` internally — they broke whenever called from inside an already-running event loop (FastAPI/MCP contexts). Instead, every caller up the stack (`flowcore.py`'s CLI commands, `cmd_selftest()`'s nested closures) is now `async def` and awaits the native methods directly; `asyncio.run()` is only ever called once, at each interface's true top-level dispatch point.
- `memory_repo.py` — `MemoryRepository`, synchronous, backed by a JSON file (`~/.flowcore/memories.json`). No `asyncio.run()` involved, safe from any context.
- `flow_repo.py` — `FlowRepository` (Sprint 15), async-only, same `data/flowcore.db` as `DocumentRepository`, same shape (`db_path` constructor override for tests, own `ensure_tables()`). Backs `flows` and `executions` — see the Flows section below.
- `database.py` — single source of truth for the SQLite path.

## Capability layer (`capability/`)

`CapabilityRegistry` + `Resolver` + per-platform adapters (`capability/adapters/{base,android,linux,termux}.py`). This is the "bridge" concept from earlier planning — capabilities like `getBattery()` resolve through the registry to whichever adapter is available on the current platform, so callers never reference `termux-battery-status` or platform-specific commands directly. Adapters share method names (`write_file`, `read_file`, `run_git`, ...) with real per-platform behavioral differences (e.g. Termux's `write_file` has richer `PermissionError` handling than Linux's) — this is intentional divergence, not copy-paste duplication.

## Passport (`passport/`)

`PassportGenerator` issues a signed (SHA-256 hash) runtime snapshot — agent identity, platform, capabilities, health, expiry — consumed by `GET /api/passport` and the Web UI's Sistema tab. As of Sprint 14, `PassportValidator`/`ValidationResult` are wired in: `GET /api/passport` runs every generated passport through `PassportValidator().validate(p)` and includes the result as a `"validation": {"valid": ..., "reason": ...}` field in the response, instead of leaving a tested-but-uncalled validator sitting unused.

## Scheduling

`runtime/job_scheduler.py`'s `JobScheduler` backs the real `flowcore.py jobs` CLI command (list/add/remove/run) via crontab/`termux-job-scheduler`. This is the only scheduler in the codebase. Sprint 14 removed `scheduler/service.py` (an APScheduler wrapper, `SchedulerService`) — it was never wired to anything beyond its own importability check inside `cmd_selftest()`, and `apscheduler` was never a declared dependency in any `requirements*.txt` in the first place.

## Flows and the Executor (`runtime/executor.py`, `storage/flow_repo.py`)

Sprint 15 rebuilt Flows from scratch rather than reviving Sprint 14's removed `executor/engine.py`/`/api/flows` stub — that pair was deleted because nothing real called it. This version is real: `FlowRepository` (`storage/flow_repo.py`, same shape as `DocumentRepository`, same `data/flowcore.db`) persists `flows` (id, name, JSON-encoded ordered step list) and `executions` (id, flow_id, status, JSON-encoded per-step results, real `started_at`/`finished_at` — the exact field the old stub never set).

A Flow's steps only ever call FlowCore's own existing capabilities — a step is `{"action": ..., "params": {...}}`, and `runtime/executor.py`'s `ACTIONS` registry maps each known action (`note`, `todo`, `agenda`, `ask`, `search`, `import_markdown`) to a `service.py` function. There's no arbitrary shell/script step type: a Flow can never run anything FlowCore couldn't already do through its other interfaces, which avoids reopening a security-review surface around executing commands from a stored (and potentially externally-authored) Flow definition.

`run_steps()` executes a Flow's steps sequentially and stops at the first failure. Deliberately no queue, no worker pool, no concurrency limit, no retry — the old `ExecutorEngine` had all of that for arbitrary concurrent async tasks, but a Flow here is one pipeline run on demand for a single user; reintroducing that machinery would be exactly the kind of speculative complexity Sprint 14 removed elsewhere in the codebase.

`service.py` owns `create_flow`/`list_flows`/`get_flow`/`delete_flow`/`run_flow`/`list_executions`/`get_execution` — the same "CLI/FastAPI/MCP call one shared implementation" discipline Sprint 14 established for notes and RAG/ask. Building the Executor also surfaced two more operations worth consolidating: `search` and `import_markdown` were duplicated ad hoc between `flowcore.py` and `mcp_server.py` (the same pattern task 2 fixed for `add_note`/`ask`); both now live in `service.py` too, with the Executor as a third caller — the same threshold that justified centralizing the first two.

Triggering is manual/API/CLI/MCP only in this version — `POST /api/flows/{id}/run`, `flowcore.py flow run <id>`, `flowcore_flow_run`. No cron/schedule integration yet; `runtime/job_scheduler.py` is untouched and a scheduled flow (cron entry that shells out to `flowcore.py flow run <id>`) can be added later without redesigning anything here.

## Agents (`agents/`) — removed

`BaseAgent` (ABC) + `AgentRegistry` had zero references anywhere else in the codebase (confirmed by repo-wide grep before removal) and no concrete agent implementation ever existed. Removed in Sprint 14 rather than left as speculative scaffolding with no consumer.

## Doctor (`doctor/service.py`)

Health-check aggregator consumed by `flowcore.py doctor`, `GET /api/status`, and the Web UI's Caps tab. Sprint 14 removed four placeholder multi-provider bridge checks (`_check_qwen_bridge`, `_check_glm_bridge`, `_check_gemini_bridge`, `_check_claude_bridge`) that only verified an env var was set (`QWEN_PORT`, `GLM_HOST`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`) with no real provider implementation behind any of them, plus the now-orphaned `_check_bridge()` helper they shared, and the empty `doctor/checks/` package. `_check_ollama` — the one bridge check with a real implementation — remains, but note it re-implements its own reachability probe (`ollama list`, then a raw socket connect to `127.0.0.1:11434`) instead of calling `runtime/ollama.py`'s `discover_ollama_endpoint()`. That means Doctor can report Ollama as unreachable on a setup where the discovery-based endpoint (e.g. a Windows-side Ollama reached from WSL2) is actually working fine for `flowcore.py ask`/`ping`. Flagged as a concrete follow-up, not fixed this sprint (out of scope for a report-only task).

## Config (`config/`)

`config/loader.py` deep-merges `config/default.json` with an optional `config/local.json` (git-ignored, per-machine overrides — e.g. this dev machine's API port had to move off `8080` due to an unrelated Docker service), then applies `FLOWCORE__SECTION__KEY`-style environment variable overrides on top. Cached after first load (`get_config()`); `reload_config()` clears the cache.

## Web UI (`web/index.html`)

Single-file, single-page app (no build step, no framework) served by FastAPI's `GET /`. Seven tabs: Início (dashboard), Sistema (battery/storage/passport), Caps (capabilities + doctor), Memórias, Notas (notes/todo/agenda + global search), Chat (RAG via `/api/ask`), Config (`/api/settings`). Talks to the backend via relative-path `fetch()` calls (`const API=''`), so it's portable across whatever host/port FastAPI actually binds to.

## Runtime (`runtime/`)

Beyond `ollama.py` and `job_scheduler.py` above: `core.py` (`FlowCoreRuntime`, `detect_platform()`), `daemon.py` (background heartbeat process), `kernel.py` (boot sequence, emits a Runtime Passport), `discovery.py`, `checkpoint.py`, `shell.py` (subprocess helpers used by the capability adapters). Sprint 14 removed `core.py`'s `init_database()`, which used SQLAlchemy to create `flows`/`executions`/`settings` tables that backed nothing (a second, separate database access path from `storage/document_repo.py`'s direct `aiosqlite` usage) — `sqlalchemy` was dropped from `requirements-api.txt` as a result, confirmed unused anywhere else in the codebase.

## Security model

| Layer | Control |
|---|---|
| Network | FastAPI binds to `127.0.0.1` only — not network-exposed |
| Privilege | No root/sudo — user-space only |
| Secrets | Credentials via environment variables (`.env`), never hardcoded |
| Code | No `os.system()`, no shell injection (verified by `scripts/audit.py`) |

## What's genuinely tested vs. manually verified

156 automated tests (`tests/`) cover: capability adapters, checkpoint, daemon, doctor, passport, API endpoints, runtime discovery/kernel, `runtime/job_scheduler.py`, `FlowRepository`, and the Executor (Sprint 15). They run in CI (`.github/workflows/ci.yml`) on every push, split into a `test-core` job (installs `requirements-core.txt` only — verifies the Termux/Android-safe tier has no hidden dependency on the API tier) and a `test-api` job (installs `requirements-api.txt`, runs `tests/test_api.py` explicitly). A `lint` job runs `ruff format --check` and `ruff check` (config in `pyproject.toml`). No deployment step exists — CI is validation-only. **The Ollama pipeline (`runtime/ollama.py`) and the Web UI still have zero automated test coverage** — everything about them was verified manually (live curl sweeps, a real headless-browser session, direct model benchmarking).

## Target platforms

| Platform | Status |
|---|---|
| Linux (WSL2, native) | Supported, primary dev target |
| Termux / Android | Supported |
| macOS | Untested this sprint, no known blockers |
| Windows (native) | Not a FlowCore runtime target — Ollama can run there and be reached from WSL2/Termux via `FLOWCORE_OLLAMA` |
| Docker | Not packaged |
