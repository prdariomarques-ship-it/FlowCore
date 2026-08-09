# LLM Router Architecture

**Status:** implemented, `runtime/llm/`. Added as a permanent architectural
requirement after Sprint 25 (Narrative Engine), realizing `ROADMAP.md`'s
previously-sketched "Version 2.0 — AI Router + Policy Engine."

**Audience:** this document is written so another engineer (human or agent
— Codex, Qwen, GLM, Jules) can extend this system without re-deriving the
design from the code. If you're adding a new LLM provider, start at "Adding
a new provider" near the bottom.

## Why this exists

Before this, FlowCore had exactly one LLM integration point:
`runtime/ollama.py`, called directly by `service.ask()` (Chat) and, briefly,
by the first draft of `runtime/narrative/`. That was fine for "one local
model, one feature." It stops being fine the moment a second backend
(a cloud model via OpenRouter, or a future direct provider) needs to exist,
because every caller would otherwise need to know which backend it's
talking to, duplicate error handling per backend, and there'd be no single
place to enforce "financial data never leaves this machine unless someone
explicitly says so."

The LLM Router is that single place. One request type in
(`LLMRequest`), one response type out (`LLMResponse`), and every decision
about *which* backend actually serves the request — and whether it's even
allowed to — lives inside the Router, not in the caller.

## The standing rule

> The rest of FlowCore must never know whether a request was executed by
> Claude, DeepSeek, OpenAI, Gemini, Ollama, or another provider.

Concretely, enforced two ways:

1. **No engine imports a provider module.** Only `runtime/llm/providers/*.py`
   files import `runtime/ollama.py`, `urllib` for OpenRouter, or any future
   provider's client. Every other module — `runtime/narrative/`,
   `service.py`, `api/router.py`, `flowcore.py`, `mcp_server.py` — only
   ever imports from `runtime.llm` (the package root) or
   `runtime.llm.router`, never `runtime.llm.providers.*`.
2. **No engine in the SCPX pipeline calls an LLM at all**, except
   `runtime/narrative/` (Layer 6), and even that only as presentation over
   an already-final `DecisionReport` — see `ARCHITECTURE.md`'s "LLM
   boundary" paragraph. This is a stricter rule than (1): most of the
   codebase isn't allowed to touch the LLM Router either, only the one
   designated presentation layer.

`service.ask()` (the pre-Sprint-25 Chat/RAG feature) is a deliberate,
flagged exception — see "Known gap: `service.ask()`" below.

## Package layout

```
runtime/llm/
    __init__.py          # re-exports the full public contract
    models.py             # LLMRequest, LLMResponse, LLMError family
    provider.py             # LLMProvider ABC — the contract every backend implements
    registry.py               # ProviderRegistry — plain dict of name -> LLMProvider
    policy.py                   # RoutingPolicy ABC + LocalFirstPolicy (the Policy Engine)
    metrics.py                    # MetricsSink ABC + NullMetrics + InMemoryMetrics
    cache.py                        # CacheBackend ABC + NullCache + InMemoryTTLCache
    budget.py                         # BudgetPolicy ABC + NoLimitBudget + CallCountBudget
    retry.py                            # with_retry() — generic, provider-agnostic
    router.py                             # LLMRouter — the single entrypoint
    providers/
        __init__.py
        ollama_provider.py                  # wraps runtime/ollama.py
        openrouter_provider.py                # OpenRouter (OpenAI-compatible), stdlib urllib
```

Every module is stdlib-only — core-tier, importable with only
`requirements-core.txt` installed (verified against a disposable venv, same
discipline as every SCPX package).

## Data flow

```
caller (e.g. runtime/narrative/engine.py)
    │
    │  builds one LLMRequest(prompt, model=None, timeout=None,
    │                        metadata={"purpose": ..., "allow_cloud": ...})
    ▼
LLMRouter.generate(request)
    │
    ├─ 1. Cache.get(cache_key_for(request)) — hit? return immediately (cached=True)
    │
    ├─ 2. registry.available_names() — ask every registered provider
    │       is_available() (cheap, no generation attempted)
    │
    ├─ 3. policy.choose(request, available) — an ORDERED subset of
    │       available providers this specific request may use.
    │       LocalFirstPolicy: always ["ollama", ...] first; a cloud
    │       provider only appears if request.metadata["allow_cloud"] is
    │       True. Empty available means empty order — never "pick
    │       anything," ever.
    │
    ├─ 4. for each provider in that order:
    │       a. budget.check(name)         — raises LLMBudgetExceededError if over limit
    │       b. with_retry(provider.generate, attempts=N)  — retries THIS
    │          provider on transient LLMError, does not move to the next
    │          provider yet
    │       c. on success: budget.record(), metrics.record_call(success),
    │          cache.set(), return LLMResponse
    │       d. on LLMError (all retries exhausted): metrics.record_call(failure),
    │          try the next provider in the order (fallback)
    │
    └─ 5. every provider in the order failed (or none were offered) ->
            raise LLMAllProvidersFailedError (or LLMProviderUnavailableError
            when the order was empty to begin with)
```

Retry (step 4b) and fallback (step 4d) are deliberately separate concerns:
retry handles *this provider* having a transient blip; fallback handles
*this provider* being down entirely. Conflating them would mean a slow-but-
working provider gets abandoned too early, or a genuinely-down provider
gets hammered with retries before falling through.

## Provider abstraction (`provider.py`)

```python
class LLMProvider(ABC):
    name: str
    def is_available(self) -> bool: ...
    def generate(self, request: LLMRequest) -> LLMResponse: ...
```

Sync, blocking by design — mirrors `runtime/ollama.py`'s own
`generate(base_url, model, prompt, timeout) -> str` shape. Async callers
(FastAPI, MCP) wrap the Router's `generate()` call in
`asyncio.to_thread()`, the same convention `service.ask()` already used for
`runtime/ollama.py` directly, before the Router existed. Providers never
need to be async-native.

**`generate()` must never raise anything other than an `LLMError`
subclass.** A provider's own exceptions (`OllamaError`, `urllib.error.URLError`,
a malformed JSON response, ...) get caught and re-raised as
`LLMProviderUnavailableError` at the provider boundary — see both shipped
providers for the pattern. This is what makes the Router's `except LLMError`
handling correct: it never needs to know what a given provider can throw.

## Provider registry (`registry.py`)

Plain `dict[str, LLMProvider]`, explicit registration (`registry.register(provider)`),
no auto-discovery or decorator magic — mirrors `runtime/observers/registry.py`'s
`ObserverRegistry` shape exactly, for the same reason: one provider per
name, no priority/fallback logic belongs in the registry itself (that's
the policy's job).

## Routing policy / Policy Engine (`policy.py`)

```python
class RoutingPolicy(ABC):
    def choose(self, request: LLMRequest, available: list[str]) -> list[str]: ...
```

Returns an **ordered subset** of `available` — the caller never picks a
provider directly, only expresses intent via `LLMRequest.metadata`.

**`LocalFirstPolicy`** (the default, wired in `service.py`): Ollama first,
always. A cloud provider is only ever added to the order when
`request.metadata.get("allow_cloud")` is `True`. This is the concrete
enforcement of "financial data, investment analysis, personal documents →
local-only, always... no automatic cloud fallback under any circumstance"
(the exact language from `ROADMAP.md`'s original Policy Engine sketch).
`runtime/narrative/`'s requests never set `allow_cloud` — a portfolio
narrative is structurally incapable of reaching a cloud provider without
someone deliberately changing that call site.

A future, more granular policy (e.g. one that reads `request.metadata["purpose"]`
and allows cloud for `"chat"` but not `"narrative"` or `"portfolio_analysis"`)
is a drop-in replacement — `LLMRouter` only depends on the `RoutingPolicy`
interface, not on `LocalFirstPolicy` specifically.

## Metrics (`metrics.py`)

```python
class MetricsSink(ABC):
    def record_call(self, provider, model, latency_ms, success, error) -> None: ...
    def snapshot(self) -> list[dict]: ...
```

`InMemoryMetrics` (wired by default in `service.py`) is a real, useful
implementation — per-provider call count, success/failure count, average
latency, last error — exposed via `GET /api/llm/status`,
`flowcore.py llm status`, and the `flowcore_llm_status` MCP tool. It is
process-lifetime only (resets on restart). A persisted, table-backed
implementation (e.g. writing to `data/flowcore.db`) is a pure addition —
swap the instance passed to `LLMRouter(..., metrics=...)`, the interface
doesn't change.

## Cache (`cache.py`)

```python
class CacheBackend(ABC):
    def get(self, key: str) -> LLMResponse | None: ...
    def set(self, key: str, response: LLMResponse) -> None: ...
```

`NullCache` is the default everywhere in this codebase today — correct,
since every current LLM caller either has call-to-call-varying context
(RAG-grounded Chat) or is narrating a live-recomputed `DecisionReport`
(stale-narrative risk if cached). `InMemoryTTLCache` is provided as a real,
working option for a future caller with high-volume, low-variance prompts
(e.g. a fixed onboarding/help-text generation), not wired in by default
anywhere. `cache_key_for(request)` hashes `model|prompt|max_tokens|temperature`
— extend it if a future caller needs `metadata` to participate in cache
key derivation.

## Budget (`budget.py`)

```python
class BudgetPolicy(ABC):
    def check(self, provider: str) -> None:  # raises LLMBudgetExceededError
    def record(self, provider: str, response: LLMResponse) -> None: ...
```

`NoLimitBudget` is the default. `CallCountBudget(max_calls={"openrouter": N},
window_seconds=...)` is a real, working starting point for capping cloud
spend by call volume. A cost-based budget (tracking real $ via
`LLMResponse.tokens_estimated` × a per-model price table) is the natural
next step and, again, a drop-in replacement for the `BudgetPolicy` passed
into `LLMRouter`.

## Retry / Fallback (`retry.py` + `router.py`)

`with_retry(fn, attempts, backoff_seconds)` is generic and provider-agnostic.
Its defaults are configured through `config/default.json` at
`llm.retry` (with the usual `config/local.json` and `FLOWCORE__...`
overrides): enablement, maximum attempts, fixed/exponential backoff,
initial/max delay, and jitter. It retries only transient provider failures
(timeouts and unavailable-provider errors except 400/401/403/404 and known
invalid/configuration failures); authentication, model-not-found, budget,
and programming errors propagate immediately. The Router records exactly one
metric for each real provider attempt, then falls through to the next provider
only after retry is exhausted. Explicit legacy arguments retain their former
fixed-backoff semantics.

## Errors (`models.py`)

```
LLMError                              (base — catch this alone if you don't care about the distinction)
├── LLMProviderUnavailableError        (one provider couldn't serve this request)
│   ├── LLMAuthenticationError          (credential/subscription/API-key problem)
│   ├── LLMModelNotFoundError            (model not installed locally / unrecognized on a cloud provider)
│   └── LLMTimeoutError                   (model load, generation, or network timed out)
├── LLMAllProvidersFailedError          (2+ providers offered, all failed differently — see below)
└── LLMBudgetExceededError               (a provider's configured budget was hit)
```

Callers of `LLMRouter.generate()` only ever need to catch `LLMError` (or a
specific subclass, for differentiated messaging) — they never need to know
or import a provider-specific exception type. Every provider maps its own
exceptions/HTTP status codes onto this same taxonomy at the boundary — see
`OllamaProvider`/`OpenRouterProvider` for the mapping table each one uses.

**Failure typing, concretely:** when exactly one provider was offered for a
request (the common case — `LocalFirstPolicy` without `allow_cloud` only
ever offers `"ollama"`) and it fails, `LLMRouter.generate()` re-raises that
provider's specific error *as-is* rather than wrapping it in
`LLMAllProvidersFailedError` — this is what lets `flowcore.py`'s `cmd_ask`
show "modelo não instalado" vs. "assinatura necessária" vs. "tempo
esgotado" through the generic Router, with zero knowledge of
`runtime.ollama`. `LLMAllProvidersFailedError` is reserved for the
genuinely ambiguous case: two or more providers were tried (e.g.
`allow_cloud=True` and both Ollama and OpenRouter failed) with no single
type honestly describing what happened.

## Wiring (`service.py` — the composition root)

```python
_llm_registry = ProviderRegistry()
_llm_registry.register(OllamaProvider())
_llm_registry.register(OpenRouterProvider())      # reads OPENROUTER_API_KEY / OPENROUTER_MODEL from env
_llm_router = LLMRouter(_llm_registry, LocalFirstPolicy(), metrics=InMemoryMetrics())
_narrative_engine = NarrativeEngine(_llm_router)  # dependency-injected, like every other engine
```

This is the *only* place in the codebase a provider class
(`OllamaProvider`, `OpenRouterProvider`) is instantiated. Everything else
depends only on the `LLMRouter`/`LLMRequest`/`LLMResponse`/`LLMError`
contracts from `runtime.llm`'s package root.

**Switching the cloud model is a config change, not a code change.**
`OpenRouterProvider` reads `OPENROUTER_MODEL` from the environment
(falling back to `"openrouter/auto"`, OpenRouter's own cost/quality
auto-router, when unset). Enabling DeepSeek — or any other model
OpenRouter proxies — is exactly:

```env
OPENROUTER_MODEL=deepseek/deepseek-v4-flash
```

or

```env
OPENROUTER_MODEL=anthropic/claude-sonnet-4
OPENROUTER_MODEL=openai/gpt-5.5
OPENROUTER_MODEL=google/gemini-2.5-pro
```

Precedence, most specific wins: `LLMRequest.model` (set by a caller for
one specific call) > `OPENROUTER_MODEL` env var > `"openrouter/auto"`
hardcoded fallback. No provider class, no `service.py` composition root
line, no `runtime/llm/` file needs to change for any of this.

## Public interfaces

| Surface | Contract |
|---|---|
| API | `GET /api/llm/status` — `{"providers": [...], "available": [...], "metrics": [...]}` |
| CLI | `flowcore.py llm status` |
| MCP | `flowcore_llm_status()` |

Two consumer-facing surfaces are backed by the Router today:
`flowcore_portfolio_narrative` / `GET /api/portfolios/{id}/narrative` /
`flowcore.py portfolio narrative` (via `runtime/narrative/`, `allow_cloud`
never set — structurally local-only) and `flowcore_ask` /
`POST /api/ask` / `flowcore.py ask` (via `service.ask()`, also
`allow_cloud` never set today). The narrative response already carries
`source` (`"llm"` | `"fallback"`) and `fallback_reason`, effectively
per-request Router status without a second round trip to
`/api/llm/status`.

## `service.ask()` migration (closed)

`service.ask()` (Chat) was migrated to the Router in the same change that
added the `LLMAuthenticationError`/`LLMModelNotFoundError`/`LLMTimeoutError`
taxonomy above — that taxonomy exists specifically *because of* this
migration: `cmd_ask` differentiates "model not installed" vs.
"subscription required" vs. "timed out" vs. "unreachable" for the user,
and the Router's original flat `LLMProviderUnavailableError` would have
lost that distinction. `flowcore.py`'s `cmd_ask`, `api/router.py`'s
`/api/ask` (502 for the three specific subclasses, 503 for everything
else), and `mcp_server.py`'s `flowcore_ask` were all updated in the same
change — `runtime.ollama`/`OllamaError` no longer appears in any of the
three. `service.ask()` never sets `metadata["allow_cloud"]`, so Chat
stays local-only by default, unchanged from before the migration.

**No remaining direct `runtime.ollama` consumers of the "generate a
response" kind exist anywhere in the codebase** — the only other places
`runtime.ollama` is still imported directly are `runtime/llm/providers/
ollama_provider.py` (correct — it *is* the Ollama provider) and a handful
of `flowcore.py`/`api/router.py` commands that introspect the local Ollama
installation itself (`ping`, `models`, `doctor`, `/api/settings`,
benchmarking) — listing installed models or checking raw connectivity is
not a "generate text" operation the Router abstracts, so these were
deliberately left as direct `discover_ollama_endpoint()`/
`discover_default_model()` calls, not migrated.

## Adding a new provider

1. Create `runtime/llm/providers/your_provider.py`. Implement `LLMProvider`:
   `name: str`, `is_available() -> bool` (cheap, no generation attempted),
   `generate(request: LLMRequest) -> LLMResponse` (raise
   `LLMProviderUnavailableError` on any failure, never a provider-specific
   exception).
2. Add it to `runtime/llm/providers/__init__.py`'s `__all__` and import.
3. Register an instance in `service.py`'s composition root:
   `_llm_registry.register(YourProvider())`.
4. If the provider needs credentials, read them from an environment
   variable (see `OpenRouterProvider`'s `OPENROUTER_API_KEY` pattern) — never
   hardcode a key, and `is_available()` must return `False` when the
   credential is missing, not raise.
5. Decide whether requests should reach it by default (add its name to
   `LocalFirstPolicy.LOCAL_PROVIDERS` if it's a local/trusted backend) or
   only opt-in (leave it out — it'll only be used when a caller sets
   `metadata["allow_cloud"]=True`, same as `OpenRouterProvider` today).
6. Write `tests/llm/test_your_provider.py` mirroring
   `tests/llm/test_ollama_provider.py` / `test_openrouter_provider.py` —
   mock at the actual network/subprocess boundary, never assume a live
   backend is running in CI.
7. No other file should need to change. If it does, that's a sign the
   abstraction leaked somewhere — worth fixing before merging.

**Realistic time estimate: well under 30 minutes** for a provider with an
OpenAI-compatible or similarly simple HTTP API — steps 1–4 are copy-and-adapt
from `openrouter_provider.py` (a working ~80-line reference
implementation), step 6 is copy-and-adapt from
`tests/llm/test_openrouter_provider.py`. The two files that change outside
`runtime/llm/providers/` are `runtime/llm/providers/__init__.py` (one
import + `__all__` entry) and `service.py` (one `register()` call) — both
one-line additions, not edits to existing logic.

## Final architecture review (post-implementation self-audit)

Verified against the actual code, not just the design intent, right after
the LLM Router shipped:

1. **New providers never require modifying `LLMRouter`.** `router.py`
   contains zero provider-name references anywhere — it only calls
   `LLMProvider`/`RoutingPolicy`/`MetricsSink`/`CacheBackend`/`BudgetPolicy`
   interface methods. Adding a cloud provider needs zero changes to
   `router.py` *or* `policy.py` (it's reachable automatically once
   registered, via `allow_cloud`). Adding a new *local/trusted* provider
   needs one line in `LocalFirstPolicy.LOCAL_PROVIDERS` — `policy.py`, not
   `router.py` — which is the documented, intended customization point.
2. **Providers are registered only through the registry.** Confirmed by
   grep: `OllamaProvider()`/`OpenRouterProvider()` are only ever
   constructed in `service.py` (the composition root) and in
   `tests/llm/`. No other file instantiates a provider class.
3. **Routing policies are fully pluggable.** `LLMRouter.__init__` takes
   `policy: RoutingPolicy` as a plain constructor argument; nothing in
   `router.py` assumes `LocalFirstPolicy` specifically.
4. **Metrics/Cache/Budget are provider-agnostic.** All three interfaces
   take the provider *name* as a plain string parameter — none special-case
   `"ollama"` or `"openrouter"` anywhere in their implementations.
5. **No provider-specific logic outside `runtime/llm/`.** Confirmed by
   grep: `OllamaProvider`/`OpenRouterProvider`/`OPENROUTER_API_KEY`/
   `OPENROUTER_MODEL` appear only inside `runtime/llm/` and in `service.py`
   (the one permitted composition root).
6. **Configuration is entirely environment-driven.** `OPENROUTER_API_KEY`
   (credential) and `OPENROUTER_MODEL` (which model OpenRouter routes to)
   — both env vars, matching `runtime/ollama.py`'s existing
   `FLOWCORE_OLLAMA`/`FLOWCORE_MODEL` convention. **This was a real gap
   found during this review** — `OPENROUTER_MODEL` did not exist in the
   first implementation (the model was a hardcoded constructor default
   only); added, tested (`tests/llm/test_openrouter_provider.py`'s
   `TestModelConfiguration`), and documented above.
7. **DeepSeek (or any OpenRouter-proxied model) via env var alone.**
   Verified directly: `OPENROUTER_MODEL=deepseek/deepseek-v4-flash` with no
   other change produces a request body with `"model":
   "deepseek/deepseek-v4-flash"` (see the test asserting this exact
   behavior).
8. **Extension process documented.** See "Adding a new provider" above.
9. **Weaknesses found and their disposition:**
   - **Fixed**: a misbehaving custom `RoutingPolicy` returning a provider
     name outside `available` (a policy bug, or a provider that stopped
     being available between the availability check and the loop) used to
     propagate `ProviderNotFoundError` out of `generate()` uncaught — not
     an `LLMError`, breaking the "callers only ever need to catch
     `LLMError`" guarantee. `router.py` now filters the policy's output
     against `available` defensively before iterating.
   - **Documented, not fixed (acceptable at this project's actual scale)**:
     `InMemoryMetrics`/`InMemoryTTLCache`/`CallCountBudget` use plain
     dicts/lists with no locking. Under concurrent access (e.g. two
     FastAPI requests calling the Router at the same time, each via
     `asyncio.to_thread`) there's a benign race in `CallCountBudget` — the
     check-then-record window isn't atomic, so a budget could briefly
     allow one or two more calls than configured under real concurrency.
     Not worth a lock for a single-user personal-automation project's
     actual traffic pattern; worth revisiting if `CallCountBudget` is ever
     used somewhere with genuine concurrent load.
   - **Documented, not fixed (correct behavior, worth being explicit
     about)**: `BudgetPolicy.record()` is only called on a *successful*
     generation — a provider that fails 100 times in a row never counts
     against its own call-count budget, only against retry/fallback cost.
     This is the intended semantic (a budget tracks billable/successful
     usage, not connection attempts), documented here so a future
     implementer doesn't "fix" it into counting failures too without
     realizing that changes the metric's meaning.
   - **Documented, not fixed (no current consumer, so no risk yet)**: the
     cache key (`cache_key_for()`) hashes `model|prompt|max_tokens|
     temperature` but not `request.metadata` — two requests with identical
     prompt/model but different `metadata["allow_cloud"]` would collide on
     the same cache key. Harmless today because `NullCache` (which never
     stores anything) is the only cache wired anywhere in this codebase;
     would need fixing (include a metadata hash, or exclude routing-only
     keys like `allow_cloud`/`purpose` from what's hashed) before any
     future caller wires in `InMemoryTTLCache` for real.

**Conclusion: the LLM Router is finalized as FlowCore's permanent AI
infrastructure.** No further architectural work is required before
additional providers, policies, or features are built on top of it.

## What was deliberately not built

Per the explicit instruction that produced this system ("leave
implementation work for later... implement only what is necessary to
validate the architecture"):

- **Only two providers** (Ollama, OpenRouter) — not one class per cloud
  vendor. OpenRouter's own `model` parameter is how a caller reaches
  GPT/Claude/Gemini/DeepSeek/etc. through the one cloud provider class
  that exists. A direct (non-OpenRouter) provider for a specific vendor is
  a future addition if a real need arises (e.g. a vendor-specific feature
  OpenRouter doesn't proxy), not built speculatively now.
- **No persisted metrics/budget tables** — `InMemoryMetrics`/`NoLimitBudget`
  are real, working, process-lifetime implementations; a persisted version
  is a drop-in replacement behind the same interface whenever real usage
  data justifies the extra complexity.
- **No cost-based budget** (real $ tracking) — `CallCountBudget` covers the
  "don't call cloud 10,000 times by accident" case; a $ budget needs a
  per-model price table that doesn't exist yet and would be guessed at
  today.
- **`service.ask()` migration** — see "Known gap" above.
