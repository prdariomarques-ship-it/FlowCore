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

`with_retry(fn, attempts, backoff_seconds)` is generic and provider-agnostic
— it retries on `LLMError` with a fixed backoff, re-raises the last error
once exhausted, and lets any non-`LLMError` (a genuine bug) propagate
immediately without being retried. The Router wraps each provider attempt
in `with_retry`, then falls through to the next provider in the policy's
order on final failure — see "Data flow" above.

## Errors (`models.py`)

```
LLMError                              (base — the only family callers should catch)
├── LLMProviderUnavailableError        (one provider couldn't serve this request)
├── LLMAllProvidersFailedError          (every offered provider failed)
└── LLMBudgetExceededError               (a provider's budget was hit)
```

Callers of `LLMRouter.generate()` only ever need to catch `LLMError` — they
never need to know or catch a provider-specific exception type.

## Wiring (`service.py` — the composition root)

```python
_llm_registry = ProviderRegistry()
_llm_registry.register(OllamaProvider())
_llm_registry.register(OpenRouterProvider())      # reads OPENROUTER_API_KEY from env; is_available()==False if unset
_llm_router = LLMRouter(_llm_registry, LocalFirstPolicy(), metrics=InMemoryMetrics())
_narrative_engine = NarrativeEngine(_llm_router)  # dependency-injected, like every other engine
```

This is the *only* place in the codebase a provider class
(`OllamaProvider`, `OpenRouterProvider`) is instantiated. Everything else
depends only on the `LLMRouter`/`LLMRequest`/`LLMResponse`/`LLMError`
contracts from `runtime.llm`'s package root.

## Public interfaces

| Surface | Contract |
|---|---|
| API | `GET /api/llm/status` — `{"providers": [...], "available": [...], "metrics": [...]}` |
| CLI | `flowcore.py llm status` |
| MCP | `flowcore_llm_status()` |

`flowcore_portfolio_narrative` / `GET /api/portfolios/{id}/narrative` /
`flowcore.py portfolio narrative` are the one existing consumer-facing
surface backed by the Router today (via `runtime/narrative/`) — its
response already carries `source` (`"llm"` | `"fallback"`) and
`fallback_reason`, which is effectively per-request Router status without
needing a second round trip to `/api/llm/status`.

## Known gap: `service.ask()`

`service.ask()` (Chat, `POST /api/ask`, `flowcore.py ask`, `flowcore_ask`)
is **not** migrated to the Router yet, deliberately. Migrating it would
change the exception types it raises (`OllamaError` family →
`LLMError` family), and `flowcore.py`, `api/router.py`, and
`mcp_server.py` all catch the `OllamaError` family specifically today —
migrating `ask()` alone would be a real backward-compatibility break, not
just an internal refactor. This is flagged explicitly (see the docstring
on `service.ask()`) as the natural next step: migrate `ask()` to build an
`LLMRequest` and call `_llm_router.generate()`, **and** update the three
call sites' exception handling from `OllamaDiscoveryError`/`OllamaError`
to `LLMError` in the same change, so the switch is atomic.

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
