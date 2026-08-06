"""RoutingPolicy -- decides which provider(s) may serve a given request,
in preference order. This is FlowCore's Policy Engine (sketched in
ROADMAP.md's "Version 2.0" section, now realized): the *only* place that
decides whether cloud is allowed for a request. No provider, no engine,
and no caller may bypass it.

Standing rule, encoded as the default policy: financial/investment/
personal data stays local-only unless a caller explicitly opts in via
request.metadata["allow_cloud"]=True -- there is never a silent,
automatic fallback from local to cloud. A caller has to say so.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from runtime.llm.models import LLMRequest

__all__ = ["RoutingPolicy", "LocalFirstPolicy"]


class RoutingPolicy(ABC):
    @abstractmethod
    def choose(self, request: LLMRequest, available: list[str]) -> list[str]:
        """Returns an ordered subset of `available` to try, most
        preferred first. An empty list means "no provider may serve
        this request" -- the Router raises LLMProviderUnavailableError,
        it never silently picks something outside this list."""


class LocalFirstPolicy(RoutingPolicy):
    """Default policy. Ollama (local) is always tried first when
    available. Cloud providers are only ever considered when the caller
    explicitly sets metadata["allow_cloud"]=True -- e.g. Narrative
    Engine requests never set it, so a portfolio narrative is
    structurally incapable of leaving the machine even if OpenRouter is
    configured, without a deliberate code change to that call site."""

    LOCAL_PROVIDERS = ("ollama",)

    def choose(self, request: LLMRequest, available: list[str]) -> list[str]:
        order = [name for name in self.LOCAL_PROVIDERS if name in available]
        if request.metadata.get("allow_cloud"):
            order += [name for name in available if name not in order]
        return order
