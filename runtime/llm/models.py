"""Canonical LLM Router request/response schema + error taxonomy.

This is the ONLY vocabulary any FlowCore code should use to talk about
an LLM call. Nothing outside runtime/llm/providers/ should ever import
a provider-specific module (runtime/ollama.py, an OpenRouter client,
...) or catch a provider-specific exception -- see docs/
LLM_ROUTER_ARCHITECTURE.md for the full rationale and the standing rule
this encodes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "LLMRequest",
    "LLMResponse",
    "LLMError",
    "LLMProviderUnavailableError",
    "LLMAuthenticationError",
    "LLMModelNotFoundError",
    "LLMTimeoutError",
    "LLMAllProvidersFailedError",
    "LLMBudgetExceededError",
]


@dataclass
class LLMRequest:
    prompt: str
    model: str | None = None  # None = provider/policy default
    timeout: float | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    # Free-form context for policies/budgets to key off -- e.g.
    # {"purpose": "narrative", "allow_cloud": False, "portfolio_id": 1}.
    # "allow_cloud" is the one metadata key the default policy inspects
    # explicitly -- see policy.py.
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "prompt": self.prompt,
            "model": self.model,
            "timeout": self.timeout,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "metadata": self.metadata,
        }


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    latency_ms: float
    tokens_estimated: int | None = None
    cached: bool = False

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "provider": self.provider,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "tokens_estimated": self.tokens_estimated,
            "cached": self.cached,
        }


class LLMError(RuntimeError):
    """Base for every error the LLM Router surfaces. Providers translate
    their own exceptions (OllamaError, urllib errors, ...) into this
    family at the provider boundary -- callers of LLMRouter never see a
    provider-specific exception type."""


class LLMProviderUnavailableError(LLMError):
    """A single provider could not serve this request (unreachable, not
    configured, model missing, ...). The Router catches this to try the
    next provider in the policy's order.

    Three more specific, provider-agnostic subclasses exist below for
    callers that want to differentiate *why* a provider failed (e.g. to
    show a user a different message for "model not installed" vs.
    "subscription required" vs. "timed out"). Every provider SHOULD raise
    the most specific subclass that applies rather than the bare base
    class -- see OllamaProvider/OpenRouterProvider for the mapping from
    each provider's own exceptions/HTTP status codes. A caller that
    doesn't care about the distinction can always just catch
    LLMProviderUnavailableError (or LLMError) and get every subclass."""


class LLMAuthenticationError(LLMProviderUnavailableError):
    """The provider is reachable but refused the request for a
    credential/subscription/API-key reason (e.g. Ollama Cloud model
    requiring a subscription, an invalid/missing cloud API key, a 401/403
    HTTP response)."""


class LLMModelNotFoundError(LLMProviderUnavailableError):
    """The requested model isn't available on this provider (not
    installed locally, or an unrecognized model string for a cloud
    provider -- typically a 404 HTTP response)."""


class LLMTimeoutError(LLMProviderUnavailableError):
    """The provider took too long -- model load, generation, or the
    underlying network call itself timed out."""


class LLMAllProvidersFailedError(LLMError):
    """Every provider the policy offered for this request failed, OR a
    single provider failed with more than one distinct error across
    retries. When exactly one provider was offered and its failure has a
    single, well-typed cause, LLMRouter.generate() re-raises that
    specific error directly instead of wrapping it here -- see
    router.py's docstring for why. This class is for the genuinely
    ambiguous case: multiple providers, multiple different failures, no
    single type would honestly describe what happened."""


class LLMBudgetExceededError(LLMError):
    """A provider's configured budget (call count, cost, ...) was hit."""
