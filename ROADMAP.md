# FlowCore Roadmap

This document outlines the planned evolution of FlowCore. See `RELEASE_NOTES.md` for what Sprint 13 delivered, `ARCHITECTURE_HEALTH_REPORT.md` for Sprint 14's architecture-quality pass, and `ARCHITECTURE.md` for the current, verified state of the system — this file is forward-looking only.

## Version 1.0 — Foundation (shipped)

| Component | Status |
|-----------|--------|
| Configuration system | Done |
| Runtime lifecycle | Done |
| Task executor | Removed in Sprint 14 — was never wired to the API, no real consumer (see `ARCHITECTURE.md`) |
| Scheduler | `runtime/job_scheduler.py` only — the unused second implementation (`scheduler/service.py`) was removed in Sprint 14 |
| REST API | Done |
| Agent framework | Removed in Sprint 14 — zero references anywhere, no concrete agent ever existed |
| CLI commands | Done |
| Daemon management | Done |
| Installation scripts | Done |
| Security audit | Done |
| CI/CD | Done — `.github/workflows/ci.yml`, added Sprint 14 (lint + format check + core tests + API tests on every push, no deployment step). Previously listed here as "Done" twice, incorrectly, before it existed; now genuinely true. |

## Version 1.1 — AI Engine (shipped, ahead of original schedule)

This version was originally planned as "connect to OpenAI, Claude, or local models." Sprint 13 delivered the local-model half of that in full — real, working, verified:

| Feature | Status |
|---------|--------|
| Local LLM integration (Ollama) | Done — auto-discovery, no hardcoded endpoint/model, classified errors |
| MCP server | Done — 12 tools, used by external MCP clients |
| RAG-grounded chat | Done — CLI, MCP, and Web UI (`/api/ask`) all share one pipeline |
| Model benchmarking | Done — `scripts/benchmark_models.py`, real 5-model comparison run |
| Web UI (first usable version) | Done — Chat + Settings tabs, verified in a real browser session |

"Connect to OpenAI or Claude" was *not* done this sprint — see Version 1.3.

## Version 1.2 — Architecture Consolidation (shipped)

Explicitly scoped as "no new features, no UI redesign, no new providers, no new AI models — only architecture quality." What Sprint 13's RC review found, fixed at the root rather than patched around:

- Fixed `storage/document_repo.py`'s `*_sync()` methods at the root: removed them entirely, made every caller `async` all the way up. No more per-call-site patching.
- Added `service.py`, a shared service layer — `add_note()`/`list_notes()`/`ask()` now exist in exactly one place, called by CLI, FastAPI, and MCP alike, instead of three divergent copies.
- Full repo audit with an explicit KEEP/REMOVE/MERGE decision per orphan module (see `ARCHITECTURE_HEALTH_REPORT.md`). Removed: `agents/` (zero references, no concrete agent ever built), `executor/engine.py` + `api/router.py`'s `/api/flows`/`/api/executions` stub (removed as a pair — the stub never called the engine), `scheduler/service.py` (unused APScheduler wrapper, `apscheduler` was never even a declared dependency), `doctor/service.py`'s four placeholder provider-bridge checks (env-var-only, no real implementation behind any of them), the empty `doctor/checks/` package, `runtime/core.py`'s dead SQLAlchemy `init_database()` (a second, unused database path).
- `PassportValidator`/`ValidationResult` given a real caller: `GET /api/passport` now validates every issued passport and returns the result, instead of sitting fully tested but never invoked.
- Added CI (`.github/workflows/ci.yml`): lint + format check (`ruff`, first run against the whole repo — 49/51 files had never been formatted), a `test-core` job (Termux/Android-safe dependency tier in isolation), a `test-api` job (API tier, explicitly running `tests/test_api.py`). No deployment step — validation only, as scoped.

## SCPX — Wealth Copilot pipeline (shipped through Sprint 24, active development)

A second major track, running in parallel with the AI-provider roadmap below.
Not originally part of Version 1.x's scope — added when the user redirected
priority toward turning FlowCore into a deterministic portfolio decision
engine. See `ARCHITECTURE.md`'s "SCPX Wealth Copilot pipeline" section for
the full architecture; summarized here for roadmap tracking:

| Sprint | Layer | Status |
|---|---|---|
| 18 | Observer (market data collection, `MarketEvent`) | Done |
| 19 | Macro Score Engine (persisted history, z-scores) | Done |
| 20 | Regime Engine (elevated/depressed/neutral classification) | Done |
| 21 | Portfolio Domain (portfolios/holdings/assets, canonical attribute schema) | Done |
| 22 | Exposure Engine (weighted classification breakdowns, concentration/HHI) | Done |
| 23 | Portfolio Impact Engine + Recommendation + Product Mapping (4 cleanly separated layers) | Done |
| 24 | Decision Engine (ranked, explainable decision queue + Decision Readiness Score) | Done |
| 25 | Narrative Engine (LLM as presentation layer only, never inside the decision pipeline) | Done |
| 26 | Alert Engine (push notifications on material decision changes) | Planned |
| 27 | Portfolio Watchlist | Planned |
| 28 | Historical Validation / Backtesting | Planned |

Standing architectural rules for this track (unchanged since Sprint 23's
correction, reaffirmed for every future sprint): every engine deterministic,
no LLM anywhere in the decision pipeline itself; never hardcode a specific
product/ticker/bank/provider outside `runtime/product_mapping/`'s config-driven
shelves; never duplicate an upstream engine's computation — always compose it.

## Version 1.3 — Hybrid AI provider architecture — superseded by Version 2.0

**Provider abstraction** (local stays default and mandatory for anything unattended/financial/cost-sensitive; cloud becomes available opt-in for interactive, quality-sensitive work — never silent fallback): this goal was achieved, in a more general form than originally sketched here, by jumping straight to Version 2.0's `runtime/llm/` (see below) rather than building a narrower Ollama-only provider interface first. What's different from the original plan: the opt-in cloud path is `OpenRouterProvider` (a meta-provider reaching GPT/Claude/Gemini/DeepSeek/etc. via one API and `ANTHROPIC`/`OPENROUTER_API_KEY`-style env config), not a dedicated `AnthropicProvider` — functionally equivalent for "make Claude available opt-in," more general for "make any cloud model available opt-in." The "explicit allow-list of which surfaces may call it" is `runtime/llm/policy.py`'s `LocalFirstPolicy`, enforced in code exactly as planned.

**Remaining known gaps, not addressed in 1.2 because they're features/UI, not architecture:**
- Web UI: Documents-browsing view, edit/delete for memories/notes, pagination past the current hard 30-item cap — all flagged in Sprint 13's UI review, none built yet.
- `doctor/service.py`'s `_check_ollama` re-implements its own reachability probe instead of calling `runtime/ollama.py`'s `discover_ollama_endpoint()` — can report Ollama unreachable on setups where discovery-based endpoint resolution actually works (see `ARCHITECTURE_HEALTH_REPORT.md`).
- `api/router.py` instantiates a fresh `MemoryRepository()`/`DocumentRepository()` inline per endpoint rather than reusing a module-level instance like `flowcore.py`/`mcp_server.py` do — harmless today (both repos are stateless), worth normalizing if the file is touched again.

## Version 2.0 — AI Router + Policy Engine — **Status: implemented**

Implemented ahead of its original sequencing (`runtime/llm/`, added after Sprint 25 as a priority directive — architecture over feature count for the remainder of that session). What was planned vs. what shipped:

- **AI Router** → `LLMRouter` (`runtime/llm/router.py`): decides which provider handles a given request via a pluggable `RoutingPolicy`, with retry-then-fallback across providers — the rest of FlowCore only ever sees `LLMRequest`/`LLMResponse`, never a provider-specific detail.
- **Policy Engine** → `LocalFirstPolicy` (`runtime/llm/policy.py`), realized exactly as specified: Ollama (local) is always tried first; a cloud provider (`OpenRouterProvider`) is only ever considered when a caller explicitly sets `request.metadata["allow_cloud"]=True` — no automatic, silent cloud fallback under any circumstance.
- **Telemetry** → `MetricsSink`/`InMemoryMetrics` (`runtime/llm/metrics.py`): per-provider call count, success/failure, average latency, last error — queryable via `GET /api/llm/status` / `flowcore.py llm status` / `flowcore_llm_status`. Process-lifetime only for now; a persisted table is a drop-in replacement behind the same interface, not built until real usage data justifies it.

Two shipped providers: `OllamaProvider` (wraps the existing local integration, zero duplicated logic) and `OpenRouterProvider` (the default cloud backend — one OpenAI-compatible meta-provider in front of GPT/Claude/Gemini/DeepSeek/many others, so no provider class per cloud vendor was needed). `runtime/narrative/` (Sprint 25) and `service.ask()` (Chat, migrated in the same architectural pass) are both dependency-injected with a Router instance rather than importing any provider module themselves — see `docs/LLM_ROUTER_ARCHITECTURE.md` for the full design, the error taxonomy (`LLMAuthenticationError`/`LLMModelNotFoundError`/`LLMTimeoutError`, added specifically to preserve `ask()`'s pre-migration differentiated error messages), data flow, and a concrete "adding a new provider" guide.

Explicitly still out of scope: `OpenAIProvider`, `GeminiProvider`, or any other provider beyond Local + OpenRouter as *separate classes* — OpenRouter's own `model` parameter already reaches those vendors. A direct (non-OpenRouter) provider for a specific vendor is a future addition if a real need arises, not built speculatively. A persisted metrics table and a cost-based (real $) budget are the same story.

## Notes

This roadmap is a living document. Version numbers here describe scope, not calendar commitments — Version 1.1 above was, in fact, delivered inside a single sprint once actually started. CI/CD now exists (`.github/workflows/ci.yml`, Sprint 14) and gates every push with lint, format, and both test tiers — no deployment step yet, so tagging/releasing to GitHub is still a manual step for now.
