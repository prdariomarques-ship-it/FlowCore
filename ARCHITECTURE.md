# FlowCore Architecture

This document describes what's actually built and wired together. The base platform sections below (entry points/service layer/storage/capability/passport/scheduling/flows/doctor/config/web UI/runtime/security) describe the state as of Sprint 15 ("Fluxos Inteligentes") and haven't needed structural changes since. The "SCPX Wealth Copilot pipeline" section covers Sprints 18–24, added on top without modifying anything above it. Where a component is real but unconnected, or where two components appear to overlap but don't, that's called out explicitly.

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

## SCPX Wealth Copilot pipeline (`runtime/observers/`, `runtime/macro_score/`, `runtime/regime/`, `runtime/portfolio/`, `runtime/exposure/`, `runtime/impact/`, `runtime/product_mapping/`, `runtime/decision/`)

A second, parallel pipeline on top of the base platform above — turns raw market data into ranked, explainable portfolio decisions. Deterministic end to end: **no LLM inside any of these layers**, ever (an LLM may only ever sit downstream as a presentation/narrative layer over already-computed output — see Sprint 25 in `ROADMAP.md`). Each layer only calls the one below it directly; nothing skips a layer, nothing duplicates a layer's computation.

```
Observer            runtime/observers/        MarketEvent (per source: treasury, dollar, vix, oil, gold)
   │                                           persisted via storage/event_repo.py's EventRepository
   ▼
Macro Score Engine   runtime/macro_score/       DimensionScore (z-score per dimension: liquidity, commodities, risk_sentiment)
   │                                           reads only persisted history — zero network calls itself
   ▼
Regime Engine        runtime/regime/            RegimeSignal (elevated/depressed/neutral/insufficient_data + threshold)
   │
   ├── Portfolio Domain   runtime/portfolio/     storage/portfolio_repo.py (portfolios/holdings/assets),
   │                                           ASSET_ATTRIBUTE_FIELDS canonical schema (12 soft attributes)
   │                                           every interface (API/CLI/MCP) derives from
   │
   ▼ (Regime + Portfolio holdings)
Exposure Engine       runtime/exposure/          weighted classification breakdowns (sector/asset_class/
   │                                           country/currency/any soft attribute) + concentration (HHI)
   ▼
Portfolio Impact      runtime/impact/            DriverImpact per macro dimension — category-only
Engine (Layer 2)                                (sector/asset_class/country/soft attribute), NEVER a
   │                                           specific ticker/fund (architectural rule, enforced by a
   │                                           regression test pinning DriverRule's field shape)
   ▼
Recommendation        runtime/impact/            generic Recommendation (action_key + human text,
Engine (Layer 3)      recommendations.py         e.g. "reduce_duration") — still zero product knowledge
   │
   ▼
Product Mapping       runtime/product_mapping/   action_key -> concrete products, entirely via external,
(Layer 4)                                       swappable config/product_shelves/*.json — the ONLY
   │                                           layer allowed to know a ticker/fund/bank name
   ▼
Decision Engine        runtime/decision/          ranked Decision Queue (priority/urgency/confidence/
(Layer 5)                                        reason_chain/recommended_products) + Decision
                                                Readiness Score (8 sub-scores) — "what should I do first,"
                                                not just "what happened"
   │
   ▼ (presentation only — never feeds back into any layer above)
Narrative Engine        runtime/narrative/         DecisionReport -> natural-language prose via the
(Layer 6)                                        existing local Ollama integration (runtime/ollama.py,
                                                same one service.ask()/Chat already use). Degrades to a
                                                deterministic, LLM-free fallback narrative (built from
                                                the same reason chains) if Ollama is unavailable
```

**Storage**: `storage/event_repo.py`'s `EventRepository` (persisted `MarketEvent` history, same `data/flowcore.db`/`aiosqlite` shape as every other repository) and `storage/portfolio_repo.py`'s `PortfolioRepository` (portfolios/holdings/assets) are the only two new tables this pipeline added — everything downstream of them (scores, regimes, exposure, impact, decisions) is computed live, never persisted, mirroring the platform's existing "recompute, don't cache" philosophy (e.g. holdings' `market_value`).

**Core-tier discipline**: every one of these packages (`observers`, `macro_score`, `regime`, `portfolio`, `exposure`, `impact`, `product_mapping`, `decision`, `narrative`) is importable with only `requirements-core.txt` installed — verified after every sprint against a disposable venv (`runtime/narrative/` imports `runtime/ollama.py`, which is stdlib-only — `urllib`, no `requests`/`yfinance`). The one recurring bug class this pipeline hit twice (Sprints 18 and 21): a package's `__init__.py` re-exporting a name from a submodule that imports `yfinance` transitively breaks importability of *every* other submodule in that package, even ones with zero yfinance dependency, because Python always executes `__init__.py` first. Fix, now a standing check for every new `runtime/<domain>/__init__.py`: re-export only dependency-free names; callers import yfinance-dependent pieces directly from their submodule.

**LLM boundary (Sprint 25, standing rule)**: `runtime/narrative/` is the *only* package in this entire pipeline allowed to call an LLM, and even then strictly as presentation over an already-final `DecisionReport` — it is never consulted by, and never feeds back into, Layers 1–5. Every other engine (Observer through Decision) remains 100% deterministic. This mirrors — and is enforced the same way as — the product-hardcoding boundary from Sprint 23 (Layer 4 is the only place a ticker may appear): one layer, one privilege, everything else stays pure.

## LLM Router (`runtime/llm/`)

A permanent architectural requirement, added after Sprint 25: the single abstraction layer between FlowCore and any LLM backend (local or cloud). Provider abstraction (`LLMProvider`), a provider registry, a routing policy (`LocalFirstPolicy` — Ollama always first, a cloud provider only ever used when a caller explicitly opts in via `request.metadata["allow_cloud"]`, never a silent fallback), metrics, cache, and budget interfaces, plus retry/fallback orchestration in `LLMRouter`. Two shipped providers: `OllamaProvider` (wraps `runtime/ollama.py`) and `OpenRouterProvider` (the default cloud backend — one OpenAI-compatible API in front of GPT/Claude/Gemini/DeepSeek/many others, so no provider-specific class per cloud vendor is needed). `runtime/narrative/` is the one SCPX consumer today, dependency-injected with a Router instance from `service.py` (the composition root) rather than importing any provider module itself. `service.ask()` (Chat) is a deliberate, flagged non-migration — see the doc below for why. Full design, data flow, and a "how to add a new provider" guide: **`docs/LLM_ROUTER_ARCHITECTURE.md`**.

**Insufficient-data-over-fabrication discipline**: every layer returns an explicit "insufficient_data" / `None`-score / empty-bucket result rather than inventing a number when there isn't enough real information — the Macro Score Engine won't score a dimension with no history, the Decision Engine's Portfolio Score excludes (never zero-fills) sub-scores with no real signal. This is the single most consistently enforced rule across the whole pipeline, checked in tests at every layer.

**Architecture correction (Sprint 23, worth remembering as precedent)**: the Portfolio Impact Engine's first draft held a hardcoded product-ticker allowlist (SGOV, GLD, ...) directly in its classification rules — caught before it shipped further, and split into the clean Layer 2/3/4 separation shown above. The lesson generalizes: a layer that turns "what's happening" into "what to do" must stay one step removed from a layer that turns "what to do" into "which specific product" — collapsing them creates exactly the tight coupling (`if treasury_up: recommend("SGOV")`) that makes an engine unreusable across different product shelves (US ETFs vs. Brazilian renda fixa vs. a private bank's own shelf, today's two shipped examples).

**Test coverage**: `tests/observers/`, `tests/macro_score/`, `tests/regime/`, `tests/portfolio/` + `test_portfolio_repo.py`, `tests/exposure/`, `tests/impact/`, `tests/product_mapping/`, `tests/decision/` — all run in CI (`test-core` and `test-api` jobs), all with the same insufficient-data/edge-case discipline as their production code (empty portfolio, missing prices, unknown dimension/shelf/decision, conflicting-signal scenarios where applicable).

## Web UI (`web/index.html`)

Single-file, single-page app (no build step, no framework) served by FastAPI's `GET /`. Eleven tabs: Início (dashboard), Dashboard (Flows/Executions), Portfólio (Sprint 21–25 — portfolio selector, live summary, macro impact, decision queue, portfolio score, LLM narrative, shelf-aware recommendations, holdings), Calendário, Integrações, Sistema (battery/storage/passport), Caps (capabilities + doctor), Memórias, Notas (notes/todo/agenda + global search), Chat (RAG via `/api/ask`), Config (`/api/settings`). Talks to the backend via relative-path `fetch()` calls (`const API=''`), so it's portable across whatever host/port FastAPI actually binds to.

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
| Linux / Debian family (WSL2) | Primary development platform. Windows hosts the local Ollama models, reached via `FLOWCORE_OLLAMA` (see `runtime/ollama.py`) — not a FlowCore runtime target itself. |
| Termux / Android | Deployment and validation target only, not part of the normal dev workflow — capabilities are developed and tested on WSL2 first, then validated on-device. Android-only capabilities (battery, wifi, clipboard, notifications, installed apps, ...) reporting "unavailable" when running on WSL2/Debian is an expected platform limitation, not a bug — `capability/adapters/linux.py` provides fallbacks where one makes sense (e.g. `getBattery`, `getDiskUsage`), and the rest simply have no non-Android equivalent. |
| macOS | Untested this sprint, no known blockers |
| Docker | Not packaged |
