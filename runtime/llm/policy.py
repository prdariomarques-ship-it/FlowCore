"""Routing policy for provider ordering and privacy boundaries."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

from runtime.llm.models import LLMRequest

__all__ = ["RoutingPolicy", "LocalFirstPolicy"]


class RoutingPolicy(ABC):
    @abstractmethod
    def choose(self, request: LLMRequest, available: list[str]) -> list[str]:
        """Return an ordered subset of available providers."""


class LocalFirstPolicy(RoutingPolicy):
    """Configurable local-first policy with explicit cloud opt-in.

    ``FLOWCORE_LLM_PROVIDER_ORDER`` accepts a comma-separated preference list,
    such as ``ollama,deepseek,glm,qwen,openrouter``. Only registered and
    available providers are returned. Cloud providers remain excluded unless
    the request sets ``metadata["allow_cloud"]`` to true.
    """

    DEFAULT_ORDER = ("ollama", "deepseek", "glm", "qwen", "openrouter", "ollama_cloud")
    LOCAL_PROVIDERS = frozenset({"ollama"})

    def __init__(self, provider_order: tuple[str, ...] | None = None) -> None:
        configured = provider_order or tuple(
            name.strip()
            for name in os.getenv("FLOWCORE_LLM_PROVIDER_ORDER", "").split(",")
            if name.strip()
        )
        self.provider_order = configured or self.DEFAULT_ORDER

    def choose(self, request: LLMRequest, available: list[str]) -> list[str]:
        ordered = [name for name in self.provider_order if name in available]
        # Keep compatibility with providers added before configuration is
        # updated, while retaining deterministic registry order.
        ordered.extend(name for name in available if name not in ordered)
        if not request.metadata.get("allow_cloud"):
            ordered = [name for name in ordered if name in self.LOCAL_PROVIDERS]
        return ordered
