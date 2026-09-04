"""ProviderRegistry -- mirrors runtime/observers/registry.py's
ObserverRegistry shape exactly (plain dict-backed, explicit
registration, no auto-discovery/decorator magic) for the same reason:
one provider per name, no priority/fallback logic belongs here -- that's
policy.py's job.
"""

from __future__ import annotations

from runtime.llm.provider import LLMProvider

__all__ = ["ProviderRegistry", "ProviderNotFoundError"]


class ProviderNotFoundError(RuntimeError):
    pass


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}

    def register(self, provider: LLMProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> LLMProvider:
        try:
            return self._providers[name]
        except KeyError:
            raise ProviderNotFoundError(f"Unknown LLM provider: {name!r}") from None

    def all(self) -> list[LLMProvider]:
        return list(self._providers.values())

    def names(self) -> list[str]:
        return list(self._providers.keys())

    def available_names(self) -> list[str]:
        return [p.name for p in self._providers.values() if p.is_available()]
