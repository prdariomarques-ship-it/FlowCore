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

## Version 1.3 — Hybrid AI provider architecture

**Provider abstraction** (local stays default and mandatory for anything unattended/financial/cost-sensitive; Claude becomes available opt-in for interactive, quality-sensitive work — never silent fallback):
- Formalize `runtime/ollama.py`'s functions behind a minimal internal provider interface (no behavior change, prep work only).
- Add `AnthropicProvider` (`ANTHROPIC_API_KEY` via `.env`), exposed as an explicitly separate, opt-in path — not wired into the default `flowcore_ask`/`/api/ask` behavior.
- Define an explicit allow-list of which surfaces may ever call it, enforced in code, not just by default.

**Remaining known gaps, not addressed in 1.2 because they're features/UI, not architecture:**
- Web UI: Documents-browsing view, edit/delete for memories/notes, pagination past the current hard 30-item cap — all flagged in Sprint 13's UI review, none built yet.
- `doctor/service.py`'s `_check_ollama` re-implements its own reachability probe instead of calling `runtime/ollama.py`'s `discover_ollama_endpoint()` — can report Ollama unreachable on setups where discovery-based endpoint resolution actually works (see `ARCHITECTURE_HEALTH_REPORT.md`).
- `api/router.py` instantiates a fresh `MemoryRepository()`/`DocumentRepository()` inline per endpoint rather than reusing a module-level instance like `flowcore.py`/`mcp_server.py` do — harmless today (both repos are stateless), worth normalizing if the file is touched again.

## Version 2.0 — AI Router + Policy Engine

The larger architectural step, once 1.3's provider abstraction and hardening are real and load-bearing, not before:

- **AI Router**: decides which provider (local vs. Claude) handles a given request based on request type, latency needs, provider health, and cost policy — without exposing provider-specific details to the rest of FlowCore.
- **Policy Engine**: has final say over whether a provider *may* be used for a given request at all (financial data, investment analysis, personal documents → local-only, always; coding/general reasoning → Claude allowed). No automatic cloud fallback under any circumstance — a blocked request explains why and asks before ever sending data externally.
- **Telemetry**: per-provider call count, latency, tokens, estimated cost, errors, fallback attempts — logged (at minimum) or queryable (if a `provider_calls` table proves worth the extra work by then).

Explicitly not in scope for 2.0 unless real usage data says otherwise: `OpenAIProvider`, `GeminiProvider`, or any other provider beyond Local + Anthropic. Every provider beyond the two that actually matter for a single-user project is speculative engineering until proven needed.

## Notes

This roadmap is a living document. Version numbers here describe scope, not calendar commitments — Version 1.1 above was, in fact, delivered inside a single sprint once actually started. CI/CD now exists (`.github/workflows/ci.yml`, Sprint 14) and gates every push with lint, format, and both test tiers — no deployment step yet, so tagging/releasing to GitHub is still a manual step for now.
