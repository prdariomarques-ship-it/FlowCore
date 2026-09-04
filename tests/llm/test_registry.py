"""Tests for runtime.llm.registry.ProviderRegistry."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _StubProvider:
    def __init__(self, name, available=True):
        self.name = name
        self._available = available

    def is_available(self):
        return self._available

    def generate(self, request):
        raise NotImplementedError


class TestProviderRegistry:
    def test_register_and_get(self):
        from runtime.llm import ProviderRegistry

        registry = ProviderRegistry()
        registry.register(_StubProvider("a"))
        assert registry.get("a").name == "a"

    def test_unknown_provider_raises(self):
        from runtime.llm import ProviderNotFoundError, ProviderRegistry

        registry = ProviderRegistry()
        with pytest.raises(ProviderNotFoundError):
            registry.get("bogus")

    def test_names_and_all(self):
        from runtime.llm import ProviderRegistry

        registry = ProviderRegistry()
        registry.register(_StubProvider("a"))
        registry.register(_StubProvider("b"))
        assert set(registry.names()) == {"a", "b"}
        assert len(registry.all()) == 2

    def test_available_names_filters_unavailable(self):
        from runtime.llm import ProviderRegistry

        registry = ProviderRegistry()
        registry.register(_StubProvider("a", available=True))
        registry.register(_StubProvider("b", available=False))
        assert registry.available_names() == ["a"]
