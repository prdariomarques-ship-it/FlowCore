# FlowCore Roadmap

This document outlines the planned evolution of FlowCore. See `RELEASE_NOTES.md` for what Sprint 13 actually delivered and `ARCHITECTURE.md` for the current, verified state of the system — this file is forward-looking only.

## Version 1.0 — Foundation (shipped)

| Component | Status |
|-----------|--------|
| Configuration system | Done |
| Runtime lifecycle | Done |
| Task executor | Built, not wired to the API (see `ARCHITECTURE.md`) |
| Scheduler | Two implementations exist; only `runtime/job_scheduler.py` is actually used |
| REST API | Done |
| Agent framework | Built, currently orphaned (zero references) |
| CLI commands | Done |
| Daemon management | Done |
| Installation scripts | Done |
| Security audit | Done |
| CI/CD | **Not done** — no `.github/workflows/` exist. Previously listed here as "Done" incorrectly; corrected in this revision. |

## Version 1.1 — AI Engine (shipped, ahead of original schedule)

This version was originally planned as "connect to OpenAI, Claude, or local models." Sprint 13 delivered the local-model half of that in full — real, working, verified:

| Feature | Status |
|---------|--------|
| Local LLM integration (Ollama) | Done — auto-discovery, no hardcoded endpoint/model, classified errors |
| MCP server | Done — 12 tools, used by external MCP clients |
| RAG-grounded chat | Done — CLI, MCP, and Web UI (`/api/ask`) all share one pipeline |
| Model benchmarking | Done — `scripts/benchmark_models.py`, real 5-model comparison run |
| Web UI (first usable version) | Done — Chat + Settings tabs, verified in a real browser session |

"Connect to OpenAI or Claude" was *not* done this sprint — see Version 1.2.

## Version 1.2 — Hybrid AI provider architecture + hardening

Two tracks, both scoped deliberately narrow (see the architecture study this session already produced for the full reasoning — not repeated here):

**Provider abstraction** (local stays default and mandatory for anything unattended/financial/cost-sensitive; Claude becomes available opt-in for interactive, quality-sensitive work — never silent fallback):
- Formalize `runtime/ollama.py`'s functions behind a minimal internal provider interface (no behavior change, prep work only).
- Add `AnthropicProvider` (`ANTHROPIC_API_KEY` via `.env`), exposed as an explicitly separate, opt-in path — not wired into the default `flowcore_ask`/`/api/ask` behavior.
- Define an explicit allow-list of which surfaces may ever call it, enforced in code, not just by default.

**Fixing what this sprint's RC review found, not papering over it:**
- Fix `storage/document_repo.py`'s `*_sync()` methods at the root (currently patched around at every known call site, not fixed in the wrapper itself).
- Fix the test-isolation bug (`pytest` writing into the real `~/.flowcore/memories.json`).
- Wire `api/router.py`'s `/api/flows`/`/api/executions` to `ExecutorEngine` for real, or remove the stub if flows aren't actually a near-term priority — currently neither, which is worse than either.
- Add CI (lint + test on push, at minimum) — this has been claimed "done" in documentation twice now without ever existing.
- Decide `agents/`'s fate: build a real consumer, or remove it. Don't leave tested-but-uncalled code (`agents/`, `PassportValidator`) accumulating indefinitely.
- Web UI: Documents-browsing view, edit/delete for memories/notes, pagination past the current hard 30-item cap — all flagged in this sprint's UI review, none built yet.

## Version 2.0 — AI Router + Policy Engine

The larger architectural step, once 1.2's provider abstraction and hardening are real and load-bearing, not before:

- **AI Router**: decides which provider (local vs. Claude) handles a given request based on request type, latency needs, provider health, and cost policy — without exposing provider-specific details to the rest of FlowCore.
- **Policy Engine**: has final say over whether a provider *may* be used for a given request at all (financial data, investment analysis, personal documents → local-only, always; coding/general reasoning → Claude allowed). No automatic cloud fallback under any circumstance — a blocked request explains why and asks before ever sending data externally.
- **Telemetry**: per-provider call count, latency, tokens, estimated cost, errors, fallback attempts — logged (at minimum) or queryable (if a `provider_calls` table proves worth the extra work by then).
- **FastAPI/MCP unification** — if, by this point, the duplicated logic between the two interfaces (documented in `ARCHITECTURE.md`) has become a real maintenance cost rather than a theoretical one, resolve it: either MCP calls FastAPI over HTTP, or shared logic moves into a service layer both import.

Explicitly not in scope for 2.0 unless real usage data says otherwise: `OpenAIProvider`, `GeminiProvider`, or any other provider beyond Local + Anthropic. Every provider beyond the two that actually matter for a single-user project is speculative engineering until proven needed.

## Notes

This roadmap is a living document. Version numbers here describe scope, not calendar commitments — Version 1.1 above was, in fact, delivered inside a single sprint once actually started. Each version will be tagged and released on GitHub once CI/CD exists to make that a real gate rather than a manual step.
