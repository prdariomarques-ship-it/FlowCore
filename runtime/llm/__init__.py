"""FlowCore -- LLM Router (permanent architectural requirement, added
after Sprint 25).

The single abstraction layer between FlowCore and any LLM backend, local
or cloud. Realizes ROADMAP.md's "Version 2.0 -- AI Router + Policy
Engine" sketch: Provider abstraction (provider.py), Provider registry
(registry.py), Routing policies (policy.py -- the Policy Engine, local-
first by default, cloud only ever opt-in per request, never a silent
fallback), Metrics (metrics.py), Cache (cache.py), Budget (budget.py),
Retry/fallback (retry.py + router.py).

No engine in the SCPX pipeline (Observer through Narrative) may import a
provider module directly -- only runtime/narrative/ consumes an
LLMRouter instance, injected by service.py, and even then only as
presentation over an already-final DecisionReport. See
docs/LLM_ROUTER_ARCHITECTURE.md for the full design and how to add a
new provider.

Deliberately core-tier: every module here is stdlib-only (the two
shipped providers use urllib, same as runtime/ollama.py already did).
"""

from __future__ import annotations

from runtime.llm.budget import BudgetPolicy, CallCountBudget, NoLimitBudget
from runtime.llm.cache import CacheBackend, InMemoryTTLCache, NullCache
from runtime.llm.metrics import InMemoryMetrics, MetricsSink, NullMetrics
from runtime.llm.models import (
    LLMAllProvidersFailedError,
    LLMAuthenticationError,
    LLMBudgetExceededError,
    LLMError,
    LLMModelNotFoundError,
    LLMProviderUnavailableError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
)
from runtime.llm.policy import LocalFirstPolicy, RoutingPolicy
from runtime.llm.provider import LLMProvider
from runtime.llm.registry import ProviderNotFoundError, ProviderRegistry
from runtime.llm.router import LLMRouter

__all__ = [
    "BudgetPolicy",
    "CacheBackend",
    "CallCountBudget",
    "InMemoryMetrics",
    "InMemoryTTLCache",
    "LLMAllProvidersFailedError",
    "LLMAuthenticationError",
    "LLMBudgetExceededError",
    "LLMError",
    "LLMModelNotFoundError",
    "LLMProvider",
    "LLMProviderUnavailableError",
    "LLMRequest",
    "LLMResponse",
    "LLMRouter",
    "LLMTimeoutError",
    "LocalFirstPolicy",
    "MetricsSink",
    "NoLimitBudget",
    "NullCache",
    "NullMetrics",
    "ProviderNotFoundError",
    "ProviderRegistry",
    "RoutingPolicy",
]
