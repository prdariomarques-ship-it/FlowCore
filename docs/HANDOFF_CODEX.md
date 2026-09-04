# Handoff to Codex — FlowCore Architecture State

**From:** Claude Code, acting as FlowCore's Chief Architect
**Date:** 2026-08-06
**Purpose:** everything a new contributor needs to continue development safely, without re-deriving the architecture from the code. Written for Codex (implementation), but applies equally to Qwen (quality gate) and GLM (review).

---

## 1. What FlowCore is, in one paragraph

A personal automation + wealth-management platform, three thin interfaces (CLI `flowcore.py`, FastAPI `api/router.py`, MCP `mcp_server.py`) over one shared `service.py` business-logic layer and one SQLite storage layer. Two major subsystems sit on top of that base: the **SCPX pipeline** (deterministic market-data-to-portfolio-decision engine, Sprints 18–25) and the **LLM Router** (`runtime/llm/`, provider-agnostic AI infrastructure, added as a priority directive right after Sprint 25). This handoff covers both, plus the base platform's known state.

---

## 2. Standing invariants — do not break these

These are load-bearing across the whole codebase. Violating any of them is a regression, not a style choice.

1. **Three entry points, one service layer.** `flowcore.py`/`api/router.py`/`mcp_server.py` never contain business logic directly for anything beyond trivial formatting — they call `service.py` and translate the result/exception into their own idiom (CLI prints, HTTP status codes, MCP `RuntimeError`). If you're about to write the same logic in two of these three files, it belongs in `service.py` instead.
2. **No SCPX engine calls an LLM**, except `runtime/narrative/` (Layer 6), and even that only narrates an already-final `DecisionReport` — it never feeds back into Layers 1–5. Every engine from Observer through Decision is 100% deterministic, tested with fixed inputs producing fixed outputs. If you're tempted to add "let the LLM decide X" anywhere in `runtime/observers/`, `runtime/macro_score/`, `runtime/regime/`, `runtime/portfolio/`, `runtime/exposure/`, `runtime/impact/`, `runtime/product_mapping/`, or `runtime/decision/` — don't. That's a product decision requiring explicit sign-off, not an engineering call.
3. **No provider-specific code outside `runtime/llm/`.** Only `runtime/llm/providers/*.py` and `service.py`'s composition root (~6 lines) may reference `OllamaProvider`, `OpenRouterProvider`, `runtime.ollama`, or any provider-specific env var (`OPENROUTER_API_KEY`, `OPENROUTER_MODEL`). Everything else — including any future engine that needs an LLM — depends only on `runtime.llm`'s `LLMRouter`/`LLMRequest`/`LLMResponse`/`LLMError` contracts, injected as a constructor dependency (see `NarrativeEngine.__init__(self, router: LLMRouter)` for the pattern).
4. **No product/ticker/bank hardcoded outside `runtime/product_mapping/`.** `runtime/impact/` classifies by *category* (sector, asset_class, country, soft attribute) only. `runtime/impact/recommendations.py` emits generic `action_key`s only. Only `config/product_shelves/*.json` (loaded by `runtime/product_mapping/mapper.py`) may name a specific ETF/fund/bank product.
5. **Cloud LLM access is opt-in per request, never silent.** `LocalFirstPolicy` only offers a cloud provider when `LLMRequest.metadata["allow_cloud"] is True`. Neither `runtime/narrative/` nor `service.ask()` sets this today — both are structurally local-only. If a future feature genuinely needs cloud, that's a product decision (what data is it sending externally, does the user know) — set `allow_cloud=True` explicitly at that one call site with a comment explaining why, don't change the default policy.
6. **Insufficient data over fabrication.** Every SCPX engine returns an explicit `"insufficient_data"` / `None`-score / empty-bucket / empty-list result rather than inventing a number when there isn't enough real information. `runtime/decision/portfolio_score.py`'s sub-scores are the clearest example — read that file before adding any new "score" or "confidence" number anywhere in the codebase.
7. **Recompute, don't persist derived state.** Holdings' `market_value`, every exposure/impact/decision/narrative computation is live, recomputed on every call, never cached to a table. Only raw inputs are persisted (`MarketEvent` history in `EventRepository`, portfolios/holdings/assets in `PortfolioRepository`). If you're about to add a table to cache a computed value "for performance," stop and ask first — this has been a deliberate choice through 8 sprints, not an oversight.
8. **Core-tier vs. API-tier dependency boundary.** `requirements-core.txt` is the Termux/Android-safe tier (stdlib + `aiosqlite` + a few others); `requirements-api.txt` adds `fastapi`/`pydantic`/`mcp`/`yfinance`/etc. Every new `runtime/<domain>/` package must specify which tier it needs, and **`__init__.py` must never eagerly import a submodule that needs the API tier** if other submodules in the same package don't — this exact bug (an `__init__.py` re-export making an unrelated, dependency-free submodule fail to import) has bitten this project twice (`runtime/observers/`, `runtime/portfolio/`). Verify any new package against a disposable core-only venv before considering it done: `python3 -m venv /tmp/venv-check && /tmp/venv-check/bin/pip install -r requirements-core.txt pytest && /tmp/venv-check/bin/python3 -m pytest -q`.

---

## 3. The SCPX pipeline — architecture map

```
Observer (runtime/observers/)
   -> MarketEvent, persisted via storage/event_repo.py's EventRepository
Macro Score Engine (runtime/macro_score/)
   -> DimensionScore (z-score per dimension: liquidity, commodities, risk_sentiment)
Regime Engine (runtime/regime/)
   -> RegimeSignal (elevated/depressed/neutral/insufficient_data)
        |
        +-- Portfolio Domain (runtime/portfolio/) -- storage/portfolio_repo.py,
        |   ASSET_ATTRIBUTE_FIELDS canonical schema (12 soft attributes)
        v
Exposure Engine (runtime/exposure/)
   -> weighted classification breakdowns + concentration (HHI)
Portfolio Impact Engine (runtime/impact/, Layer 2)
   -> DriverImpact per macro dimension -- category-only, NEVER a ticker
Recommendation Engine (runtime/impact/recommendations.py, Layer 3)
   -> generic Recommendation (action_key + text) -- still zero product knowledge
Product Mapping (runtime/product_mapping/, Layer 4)
   -> action_key -> concrete products, via config/product_shelves/*.json
Decision Engine (runtime/decision/, Layer 5)
   -> ranked Decision Queue + Decision Readiness Score
Narrative Engine (runtime/narrative/, Layer 6)
   -> DecisionReport -> prose, via the LLM Router. Presentation only.
```

Each layer is a small package (5-10 files, each under ~150 lines) composing the layer below it directly — never skipping a layer, never duplicating a layer's computation. `runtime/decision/engine.py` is the best example to study for "how to compose 3 upstream engines without duplicating any of their logic."

**Full detail:** `ARCHITECTURE.md`'s "SCPX Wealth Copilot pipeline" section. **Sprint-by-sprint history + what's planned next:** `ROADMAP.md`'s "SCPX — Wealth Copilot pipeline" section (Sprints 26–28: Alert Engine, Portfolio Watchlist, Historical Validation/Backtesting — not started).

**A precedent worth internalizing:** the Portfolio Impact Engine's first draft (Sprint 23) held a hardcoded ticker allowlist directly in its classification rules. It was caught and corrected *before* it shipped further, splitting into the clean Layer 2/3/4 separation above. If you find yourself writing `if dimension == "liquidity": recommend("SGOV")` anywhere, that's this exact mistake recurring — stop and route it through `runtime/product_mapping/` instead.

---

## 4. The LLM Router — architecture map

```
runtime/llm/
    provider.py     -- LLMProvider ABC (name, is_available(), generate())
    registry.py       -- ProviderRegistry, plain dict, explicit registration
    policy.py           -- RoutingPolicy ABC + LocalFirstPolicy (the Policy Engine)
    metrics.py            -- MetricsSink ABC + NullMetrics + InMemoryMetrics
    cache.py                 -- CacheBackend ABC + NullCache + InMemoryTTLCache
    budget.py                  -- BudgetPolicy ABC + NoLimitBudget + CallCountBudget
    retry.py                     -- with_retry(), generic, provider-agnostic
    router.py                      -- LLMRouter, the single entrypoint
    providers/
        ollama_provider.py            -- wraps runtime/ollama.py
        openrouter_provider.py          -- default cloud backend (meta-provider)
```

**Full detail, including a step-by-step "add a new provider in under 30 minutes" guide and a post-implementation self-audit:** `docs/LLM_ROUTER_ARCHITECTURE.md`. Read this before touching `runtime/llm/` — it answers "why is X designed this way" for every file.

**Current consumers:** `runtime/narrative/` (SCPX Layer 6) and `service.ask()` (Chat). Both are injected with the same `_llm_router` singleton constructed in `service.py`. Neither sets `allow_cloud`.

**Error taxonomy** (`runtime/llm/models.py`) — use this instead of inventing new exception types:
```
LLMError
├── LLMProviderUnavailableError
│   ├── LLMAuthenticationError    (credential/subscription/API-key problem)
│   ├── LLMModelNotFoundError      (model not installed/unrecognized)
│   └── LLMTimeoutError              (load/generation/network timeout)
├── LLMAllProvidersFailedError     (2+ providers tried, all failed)
└── LLMBudgetExceededError          (a provider's budget was hit)
```
A new provider maps its own exceptions/HTTP codes onto this taxonomy at its own boundary (see `ollama_provider.py`/`openrouter_provider.py` for the pattern) — callers of `LLMRouter.generate()` never need to know the provider-specific type.

---

## 5. Extension points (where to add things)

| You want to... | Do this |
|---|---|
| Add a new LLM provider (e.g. a direct Anthropic/Gemini SDK) | `docs/LLM_ROUTER_ARCHITECTURE.md`'s "Adding a new provider" section, step by step. Register in `service.py`. |
| Add a new product shelf (a specific bank's product list) | Drop a new `config/product_shelves/<name>.json` — no code change. See `us_etf.json`/`br_renda_fixa.json` for the shape. |
| Add a new macro dimension (e.g. inflation, once a real data source exists) | `runtime/observers/`'s `_default_observers()` + `runtime/macro_score/dimension.py`'s `DIMENSIONS` dict. Everything downstream (Regime, Impact, Decision) picks it up automatically *if* you also add a `DriverRule` in `runtime/impact/rules.py` for it — until then it'll compute a regime signal that no Impact driver consumes, which is fine (harmless, just unused). |
| Add a new soft asset attribute | `runtime/portfolio/attributes.py`'s `ASSET_ATTRIBUTE_FIELDS` tuple — every interface (API/CLI/MCP schema, Exposure Engine's `by_attribute()`) derives from this one list automatically. MCP is the one exception (needs a real Python signature) — there's a regression test (`tests/portfolio/test_attributes_schema.py`) pinning that MCP's hand-written signature matches the tuple; update both together. |
| Add a new routing policy (e.g. per-purpose cloud allowance) | Implement `RoutingPolicy`, pass it to `LLMRouter(...)` in `service.py` instead of `LocalFirstPolicy()`. `LLMRouter` only depends on the interface. |
| Add persisted metrics/cost-based budget | Implement `MetricsSink`/`BudgetPolicy`, swap the instance passed to `LLMRouter(...)`. No interface change needed — `InMemoryMetrics`/`CallCountBudget` are real starting points, not stubs to throw away. |

---

## 6. Known gaps / explicitly deferred work (not bugs — read before "fixing")

- **`flowcore.py` is ~2,900 lines**, the largest file in the repo by a wide margin. Not touched this session (out of scope for "architecture over feature count"). If you're adding substantial new CLI surface, consider whether it belongs in a new module instead of growing this file further — `ARCHITECTURE_HEALTH_REPORT.md` has flagged this since Sprint 14.
- **`doctor/service.py`'s `_check_ollama`** re-implements its own reachability probe instead of using `runtime/ollama.py`'s `discover_ollama_endpoint()` (and, now, could use `runtime/llm/`'s `OllamaProvider().is_available()` instead). Can report Ollama unreachable on a setup where `flowcore.py ask` actually works. Small, well-understood fix, not done — flagged since Sprint 14.
- **`api/router.py` instantiates fresh `MemoryRepository()`/`DocumentRepository()` per endpoint** instead of a module-level singleton like `flowcore.py`/`mcp_server.py` use. Harmless (both repos are stateless) but inconsistent.
- **Sprint 26–28 (Alert Engine, Portfolio Watchlist, Historical Validation/Backtesting)** are planned in `ROADMAP.md` but not started. Each should follow the same per-sprint discipline documented there (implement, tests, API, CLI, MCP, Web UI, Playwright, full pytest, core-only venv, CI, docs) and the same "deterministic engine, generic abstractions, no hardcoded providers/products" rules as everything above.
- **DI futuro and Notícias Observer dimensions** have no real data source (API MDS B3 is 404, no news provider decided) — deliberately absent from `DIMENSIONS`, not a bug.
- **`InMemoryMetrics`/`InMemoryTTLCache`/`CallCountBudget` aren't lock-protected.** Under real concurrent load there's a benign race (budget could allow a call or two over its limit briefly). Not worth fixing at this project's actual single-user scale; worth revisiting if traffic patterns ever change. Documented in `docs/LLM_ROUTER_ARCHITECTURE.md`'s "Final architecture review."
- **The LLM Router's cache key doesn't hash `request.metadata`.** No risk today (`NullCache` is the only cache wired anywhere), but fix this (hash a stable subset of metadata, or exclude routing-only keys) before wiring `InMemoryTTLCache` into any real call site.

---

## 7. Verification checklist (run before considering any change done)

```bash
ruff check . && ruff format --check .
python3 -m pytest -q                                    # full suite
python3 -m venv /tmp/venv-check && \
  /tmp/venv-check/bin/pip install -r requirements-core.txt pytest && \
  /tmp/venv-check/bin/python3 -m pytest -q               # core-only tier
```
Then, for anything touching an interface: live-verify via CLI (`python3 flowcore.py <command>`), a running server (`python3 flowcore.py serve` + `curl`), and MCP tool registration (`await mcp.list_tools()`). For Web UI changes: an actual headless-browser session (Playwright — install fresh, verify, uninstall; not a project dependency), not just reading the HTML.

**CI note (as of this handoff):** GitHub Actions was experiencing an infrastructure outage (`Failed to resolve action download info: Service Unavailable`, and later the workflow-trigger mechanism itself stopped registering new runs) for roughly the last hour of this session. `Format & Lint` passed on every attempted run; `Core tests`/`API tests` failed at the "Set up job" step before checkout even ran — this is unambiguously GitHub-side, not a code problem, confirmed by full local verification (pytest + core-only venv, both green, multiple times, on the final commit). **Re-run CI on the latest `main` commit once GitHub's status recovers** before assuming anything is broken.

---

## 8. Where to read more

- `ARCHITECTURE.md` — what's built and wired, base platform + SCPX pipeline + LLM Router sections.
- `ARCHITECTURE_HEALTH_REPORT.md` — scored debt assessment, updated through this session.
- `ROADMAP.md` — forward-looking plan, Version 2.0 (LLM Router) marked implemented with a point-by-point mapping against what shipped.
- `CHANGELOG.md` — [1.3.0]–[1.5.0] cover Sprints 24–25 and the LLM Router.
- `docs/LLM_ROUTER_ARCHITECTURE.md` — the deep-dive on `runtime/llm/` specifically, including the post-implementation self-audit against a 9-point checklist and the "adding a new provider" guide.

---

## 9. Sprint 25 — Doctor Flow vertical slice (Qwen quality gate)

**From:** Claude Code, acting as FlowCore's Runtime/Architecture owner
**Date:** 2026-08-10
**Purpose:** quality-gate handoff for Qwen. Codex's gate was skipped for this slice — confirmed (see below) that `runtime/executor.py` (Execution Engine, Codex's domain) is untouched and outside the Doctor Flow's dependency graph, so there is nothing in Codex's domain to review here.

**Commit:** `598e4909c7740df40b0068ea03036a4a38172e7e` (`origin/main`), two commits:
- `a9179c7` — feat(runtime): wire Doctor Flow end-to-end
- `598e490` — test(runtime): cover Doctor Flow

**What shipped:** the first real end-to-end FlowCore flow — `USER → CLI (flowcore.py doctor) → Runtime (FlowCoreRuntime.run_doctor()) → Capability Registry (ProviderResolver) → Doctor Capability (getCpuInfo/getMemoryInfo/getDiskUsage on LinuxAdapter) → Execution (real /proc + os.getloadavg() reads, no hardcoded data) → Observability (loguru, existing convention) → History (~/.flowcore/flowcore.doctor.json, same convention as flowcore.runtime.json)`. `DoctorService` (35 pre-existing component checks) is folded into the same report under `components`.

**Public contract:**
```python
from runtime.core import FlowCoreRuntime
report = FlowCoreRuntime().run_doctor()
# {generated_at, environment, cpu, memory, disk, components}
# cpu/memory/disk are CapabilityResult.to_dict(); components is DoctorReport.to_dict()
```

**Already verified by Claude, with reproducible evidence (commands run in a detached worktree at the exact commit, no code changed):**
- JSON round-trip: `json.loads(json.dumps(report)) == report` — passes.
- Safe degradation: `ProviderResolver(registry=CapabilityRegistry(adapters=[])).resolve("getCpuInfo"/"getMemoryInfo"/"getDiskUsage")` returns `CapabilityResult.fail(...)`, never raises.
- `runtime/executor.py` unchanged: `git hash-object runtime/executor.py` == blob at baseline `584d380` (`1f404ec57eda1b20f0487c99e7dc2449afe9b116`).
- No `executor`/`ExecutionEngine` reference anywhere in the Doctor Flow's module closure (`runtime/core.py`, `capability/resolver.py`, `capability/registry.py`, `capability/adapters/{base,linux,android,termux}.py`, `doctor/service.py`, `runtime/daemon.py`, `runtime/shell.py`, `runtime/ollama.py`) — `grep -rn "executor\|ExecutionEngine"` across all of them returns 0 matches.
- Import graph of that same closure is acyclic (verified via `ast`-based static analysis, not just top-level regex — it walks every function body, which is how the `doctor.service -> runtime.daemon` local import inside `_check_daemon_state` was caught).
- `pytest -q` — 459 passed, 14 skipped, 0 failures, 0 regression (was 446/14 before this sprint).
- `ruff check .` and `ruff format --check .` — clean.

**What Qwen should specifically check (outside Claude's architecture-gate scope):**
- Security: `LinuxAdapter.get_memory_info()` (`capability/adapters/linux.py`) reads `/proc/meminfo` and catches a broad `except Exception`. Confirm that's an acceptable breadth here (no secrets in that file, read-only, no shell-out) or tighten it.
- Test depth: `tests/test_runtime_core.py` and the additions to `tests/test_capability.py` cover the happy path and the "no adapter" path. No test currently exercises a malformed `/proc/meminfo` or `os.getloadavg()` raising `OSError` on a platform that lacks it (the code path exists in `get_cpu_info`'s `except (OSError, AttributeError)`, just untested).
- Whether 35 `DoctorService` checks folded into one CLI command is too much output for a "quick" `flowcore doctor` — a UX/quality call, not an architecture one.

**Known gaps, deliberately left as backlog (not defects):**
- No live database-connectivity check migrated into `DoctorService` (the old ad-hoc `cmd_doctor` had one; dropped in the consolidation — see commit `a9179c7` message for the trade-off).
- `get_cpu_info`/`get_memory_info` are only implemented on `LinuxAdapter`; on real Android/Termux they fall through to the base-stub `CapabilityResult.fail("... not supported")` — safe, but not real data on those platforms yet.
- **Sprint-number collision:** this document's own section 8 already states "`CHANGELOG.md` — [1.3.0]–[1.5.0] cover Sprints 24-25 and the LLM Router" — i.e. "Sprint 25" was already used for the LLM Router in this repo's history, before being reused for this Doctor Flow slice. Worth reconciling sprint numbering across agents before it causes confusion in `ROADMAP.md`/`CHANGELOG.md`.
