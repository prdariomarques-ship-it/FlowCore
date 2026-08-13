"""Tests for runtime.observers.registry.ObserverRegistry."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

yfinance = pytest.importorskip("yfinance")

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestObserverRegistry:
    def test_register_and_get(self):
        from runtime.observers.base import Observer
        from runtime.observers.registry import ObserverRegistry

        class DummyObserver(Observer):
            source = "dummy"
            category = "test"

            def observe(self):
                return []

        reg = ObserverRegistry()
        reg.register(DummyObserver())
        assert reg.get("dummy").source == "dummy"

    def test_get_unknown_raises(self):
        from runtime.observers.base import ObserverError
        from runtime.observers.registry import ObserverRegistry

        reg = ObserverRegistry()
        with pytest.raises(ObserverError, match="Unknown observer"):
            reg.get("bogus")

    def test_all_and_names(self):
        from runtime.observers.base import Observer
        from runtime.observers.registry import ObserverRegistry

        class A(Observer):
            source = "a"
            category = "test"

            def observe(self):
                return []

        class B(Observer):
            source = "b"
            category = "test"

            def observe(self):
                return []

        reg = ObserverRegistry()
        reg.register(A())
        reg.register(B())
        assert set(reg.names()) == {"a", "b"}
        assert len(reg.all()) == 2


class TestDefaultRegistry:
    def test_seven_default_observers_registered(self):
        from runtime.observers.registry import registry

        names = set(registry.names())
        # The original 7 core observers remain registered (backward
        # compatibility); the registry was expanded with BR/US/EU/Asia
        # equities, rates, FX and commodities observers.
        assert {"treasury", "dollar", "vix", "oil", "gold", "usd_jpy",
                "treasury_30y"} <= names
        assert len(names) >= 25
