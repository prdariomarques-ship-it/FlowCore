# FlowCore Architecture Health Report

**Sprint 14 — Architecture Consolidation, task 6.** Scored against the codebase as it stands after tasks 1–5 of this sprint (service layer added, dead code removed, CI wired). Every score below is backed by a concrete, checkable finding — grep output, line counts, or an actual isolated test run — not an impression. Where I disagree with my own numbers being generous, I say so.

## Scorecard

| Dimension | Score | Trend this sprint |
|---|---|---|
| Maintainability | 7 / 10 | ↑ (was ~4/10 before Sprint 14) |
| Modularity | 8 / 10 | ↑ |
| Coupling | 8 / 10 | ↑↑ (biggest single improvement) |
| Cohesion | 6 / 10 | → (unchanged — `flowcore.py` wasn't split) |
| Duplication | 8 / 10 | ↑↑ |
| Technical debt | 7 / 10 | ↑↑↑ (largest category of change this sprint) |
| **Overall** | **7.3 / 10** | **Was ~5/10 at Sprint 13 close** |

Scale: 10 = no known issues in this dimension. 1 = actively blocking development. A single-developer personal-automation project with three thin interfaces over one storage layer should realistically top out around 8–9 on most axes — a 10 would mean over-engineering for the actual scale of the problem.

---

## Maintainability — 7/10

**What improved:** the recurring bug pattern this whole project has fought — `asyncio.run()` called from inside an already-running event loop — is now fixed at the root instead of patched at each call site. `storage/document_repo.py`'s `*_sync()` wrappers are gone entirely; every caller up through `flowcore.py`, `api/router.py`, and `mcp_server.py` is `async` end-to-end. This was the single most valuable change in the sprint for future maintainability: it removes an entire class of bug that had already bitten the project twice before this sprint (both FastAPI and MCP call sites).

**What's still a liability:** `flowcore.py` is 1,617 lines and 57 functions — by far the largest file in the repo (the next-largest package, `capability/`, is 1,679 lines spread across *nine* files). `cmd_selftest()` alone is 341 lines. It mixes argument parsing, ~15 command implementations, a full self-test harness, and inline availability probes in one file. This isn't a correctness problem — it works, and the tests confirm it — but it's the file most likely to develop real bugs a year from now, because it's the one place in the codebase where "just find the right spot" requires scanning hundreds of lines. Concrete recommendation: next time `flowcore.py` needs a non-trivial change, split `cmd_selftest()`'s checks into a `selftest.py` module the way `doctor/service.py` already models (a list of check functions + a runner), rather than growing the inline version further.

## Modularity — 8/10

Top-level packages have clear, single-purpose boundaries: `storage/` (persistence), `capability/` (platform abstraction), `doctor/` (health checks), `passport/` (identity/validation), `config/` (settings), `runtime/` (process lifecycle + Ollama + scheduling). Import-graph check (below) confirms no package imports "upward" — `storage` never imports `runtime`, `runtime` never imports `api`, etc. No circular imports anywhere in the 13 core modules checked.

```
storage    → config
runtime    → config
capability → runtime
doctor     → runtime
installer  → runtime
service    → runtime, storage
api        → service                      (clean — goes through the service layer only)
mcp_server → service, runtime.ollama (errors only), storage (read-only ops)
flowcore   → config, runtime, storage      (CLI is the one interface still calling storage directly for everything)
```

The one structural oddity: `flowcore.py` is simultaneously the CLI *and* the project's de facto entry-point module — it isn't really "a module with a job," it's where 15 different jobs happen to live because that's where `argparse` dispatch is. That's a naming/scope issue more than a real modularity violation (see Maintainability above).

## Coupling — 8/10, the sprint's biggest win

Before this sprint, `api/router.py` and `mcp_server.py` each independently reimplemented note-taking (with *different* label mappings — `"Nota"` vs `"Note"` for the same kind) and the RAG/ask flow. That's gone: `service.py` now owns `add_note()`, `list_notes()`, and `ask()`, and both interfaces call it instead of storage directly. `api/router.py` in particular is now coupled to exactly one thing for its business-logic endpoints: `service`. That's about as low as coupling gets for a project with three independent processes and no message bus between them — the alternative (MCP calling FastAPI over HTTP, or a shared daemon) would trade this simplicity for operational complexity that a single-user project doesn't need yet, as `ARCHITECTURE.md` already notes.

Two minor residual coupling smells, both harmless in practice but worth naming:
- `mcp_server.py` imports `storage` directly for read-only tools (`flowcore_docs`, `flowcore_search`, `flowcore_stats`, ...) rather than through `service.py`. This is a deliberate, defensible choice — those tools have no real logic to share, just a repository call — but it does mean "does this interface talk to service or storage" isn't a single consistent rule; it depends on whether the operation has business logic behind it.
- `doctor/service.py`'s `_check_ollama` talks to Ollama directly (`ollama list` subprocess, then a raw `socket.connect(("127.0.0.1", 11434))`) instead of going through `runtime/ollama.py`'s `discover_ollama_endpoint()` — the same auto-discovery module every other Ollama-touching code path in the project uses. This is coupling to the *wrong* thing: Doctor is coupled to a hardcoded default instead of to the shared discovery logic. See Technical Debt below — this is a real (if minor) correctness gap, not just a style note.

## Cohesion — 6/10, unchanged this sprint

Most packages score well individually: `storage/` does persistence and nothing else, `passport/` does identity issuance and validation and nothing else, `capability/` does platform-adapter resolution and nothing else. The drag on this score is entirely `flowcore.py`: one file responsible for CLI parsing, ~15 unrelated command behaviors (notes, search, sync, watch, obsidian integration, daily summaries, health checks, a full self-test suite), and inline dependency-availability probing. Individually each function is cohesive; the *file* is not. This is the same finding as Maintainability's, from a different angle — flagged as its own line item because "one file, many unrelated responsibilities" is specifically what cohesion measures, and it's worth tracking as its own number so it doesn't get lost inside a more general maintainability score.

## Duplication — 8/10, the sprint's second-biggest win

The literal duplication this sprint's mandate called out (task 2: "the same operation must never be implemented twice") is resolved for the two operations that actually had diverging copies: note-taking and RAG/ask. Verified by grep — `NOTE_KIND_LABELS` now exists in exactly one place (`service.py`), not two.

What's *not* duplication, correctly left alone: the capability adapters' shared method names (`write_file`, `read_file`, `run_git`) across `android.py`/`linux.py`/`termux.py` look like copy-paste at a glance but implement genuinely different platform behavior (e.g., Termux's `write_file` has richer `PermissionError` handling) — collapsing these into one implementation would be the wrong move, not a cleanup.

What's a subtler form of duplication worth naming: `doctor/service.py`'s `_check_ollama` re-implements Ollama reachability logic that `runtime/ollama.py` already solved more thoroughly (multi-host discovery vs. a single hardcoded `127.0.0.1:11434`). This isn't identical code, so a naive duplication scanner wouldn't catch it — but it's the same *duplicated intent* task 2 was written to eliminate, just expressed as two different implementations of "check if Ollama is up" instead of two copies of the same code. Listed under Technical Debt as a concrete follow-up.

## Technical Debt — 7/10, largest single area of improvement

Debt removed this sprint (with LOC/impact where it's measurable):
- `agents/` package (`BaseAgent`, `AgentRegistry`) — zero references anywhere, no concrete agent ever built. Removed.
- `executor/engine.py` (`ExecutorEngine`) + `api/router.py`'s `/api/flows`/`/api/executions` in-memory stub — removed together, since the stub never called the engine it was ostensibly for.
- `scheduler/service.py` (`SchedulerService`, an APScheduler wrapper) — only ever instantiated inside a self-test importability check; `apscheduler` was never even a declared dependency. Removed.
- `doctor/service.py`'s four placeholder provider-bridge checks (`_check_qwen_bridge`, `_check_glm_bridge`, `_check_gemini_bridge`, `_check_claude_bridge`) — env-var-presence checks with no real implementation behind any of them. Removed, along with the now-orphaned `_check_bridge()` helper and the empty `doctor/checks/` package.
- `runtime/core.py`'s `init_database()` — a second, unused SQLAlchemy-backed database path for `flows`/`executions`/`settings` tables that backed nothing. Removed; `sqlalchemy` and `pydantic-settings` dropped from `requirements-api.txt`, both confirmed to have zero remaining usage.
- `PassportValidator`/`ValidationResult` — previously fully tested but never called anywhere in the running application. Now wired into `GET /api/passport`.
- No CI ever existed, despite being listed as "Done" in `ROADMAP.md` on two prior occasions. Now real: `.github/workflows/ci.yml`, verified green on an actual push (not just locally), running lint, format check, and both dependency-tier test suites in isolation.
- Ruff had never been run against this codebase. First run surfaced 52 findings across 5 rule categories; each was individually triaged (fixed vs. deliberately configured as an ignored/per-file rule, with the reasoning for each recorded in `pyproject.toml`'s comments and the task-5 commit message) rather than either blanket-ignored or blindly auto-fixed. `ruff format` had also never been run — 49 of 51 Python files got their first-ever formatting pass, verified with a full `py_compile` sweep and a full test run before and after.

Debt remaining, ranked by what would move the needle most next:
1. **`flowcore.py`'s size/cohesion** (see above) — the only item on this list that's a structural refactor, not a removal. Highest effort, and correctly out of scope for a "no new features" sprint, but the next sprint that touches `flowcore.py` substantially should budget for splitting `cmd_selftest()` out.
2. **`doctor/service.py`'s `_check_ollama` bypasses discovery** — small fix (call `discover_ollama_endpoint()` instead of hardcoding `127.0.0.1:11434`), but a real one: Doctor can report Ollama unreachable on a working WSL2→Windows or Termux/LAN setup where `flowcore.py ask` succeeds fine, because Doctor never uses the same discovery path.
3. **`api/router.py`'s repo-instantiation inconsistency** — it creates a fresh `MemoryRepository()`/`DocumentRepository()` inline per endpoint, while `flowcore.py` and `mcp_server.py` both use a module-level singleton. Both repos are stateless (re-read from disk on each call), so this is cosmetic today, not a bug — but it's inconsistent for no reason, and worth normalizing the next time that file is opened.
4. **Zero automated coverage for `runtime/ollama.py` and the Web UI** — both were verified manually this project (curl sweeps, a live headless-browser session, real model benchmarking) but have no regression protection. Not attempted this sprint; flagged since it's the largest test-coverage gap in an otherwise well-tested codebase (135 tests, 100% passing, now gated in CI).

---

## What the numbers are built on

- 135 automated tests, 100% passing, now running in GitHub Actions CI on every push (verified against a real run, not just a local simulation) — split into a core-tier job (`requirements-core.txt` only) and an API-tier job (`requirements-api.txt`, `tests/test_api.py` explicitly), each installed into an isolated venv and verified independently before being trusted in the CI config.
- `ruff check .` and `ruff format --check .`: clean, zero findings, config in `pyproject.toml`.
- Import-graph and circular-import check: 13 core modules import-tested individually, all succeed, no cycles found.
- `~9,650` lines of Python across the repo; `flowcore.py` alone accounts for ~17% of that in a single file.
- `ARCHITECTURE.md` and `ROADMAP.md` updated alongside this report — both had drifted out of date describing modules removed in task 4 (agents/executor/scheduler) as if they still existed, and `PassportValidator` as uncalled when it's now wired. Stale architecture docs are themselves a maintainability cost; fixing them was treated as part of this report, not a separate task.

## Recommendation for what comes next

Given the remaining debt list above, the highest-leverage next step is small and targeted: fix `doctor/service.py`'s Ollama check to use `discover_ollama_endpoint()` (item 2) — it's the one piece of remaining debt that's an actual behavioral gap rather than cosmetic, and it's a low-risk, single-function change. Everything else on the list (the `flowcore.py` split, the `api/router.py` repo-instantiation cleanup, test coverage for `runtime/ollama.py`/the Web UI) is real but lower-urgency, and better tackled when there's a substantive reason to be in those files anyway rather than as standalone busywork.

---

## Addendum — SCPX pipeline (Sprints 18–24), light-touch update

Not a full re-score (that would need its own dedicated pass across ~8 sprints of new code); this note exists because the standing instruction is to touch this report at the end of every sprint "if needed" — here's what changed and why it doesn't move the scorecard above.

The SCPX pipeline (`runtime/observers/`, `macro_score/`, `regime/`, `portfolio/`, `exposure/`, `impact/`, `product_mapping/`, `decision/`) was built as a genuinely separate, additive track — it does not touch `flowcore.py`'s size problem (item 1 above), does not touch `doctor/service.py` (item 2), does not touch `api/router.py`'s repo-instantiation pattern (item 3). Its own internal health, judged the same way as the rest of this report:

- **Duplication**: consistently avoided by composition — `ExposureEngine.compute_concentration()` is reused as-is by `ImpactEngine`, `ImpactEngine` is reused as-is by `DecisionEngine`, `runtime/product_mapping/` is called, never reimplemented, by both `service.py` and `runtime/decision/engine.py`. No engine recomputes a number an upstream layer already produced.
- **Cohesion**: each package is single-purpose and small (the largest, `runtime/decision/`, is 8 files each under ~120 lines) — the opposite of `flowcore.py`'s problem.
- **Test coverage**: every layer has dedicated unit tests plus API endpoint tests, all core-tier-verified (no hidden `requirements-api.txt` dependency) except where a layer genuinely needs `yfinance` (`observers`, `portfolio.asset_provider`/`valuation`) — those are `pytest.importorskip`-gated, consistent with the rest of the codebase's core/API tier split.
- **One real recurring bug class**: the `__init__.py` eager-import trap (see `ARCHITECTURE.md`'s SCPX section) — caught and fixed twice (Sprints 18, 21), now a standing checklist item for any new `runtime/<domain>/__init__.py`. Worth naming here because it's exactly the kind of pattern this report exists to track over time.

No change to the overall 7.3/10 scorecard — the new code doesn't touch any of the four items still open above, and its own quality is high enough not to introduce new debt.
