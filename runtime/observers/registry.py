"""Observer registry — plain name→Observer lookup.

Mirrors capability/registry.py's explicit-list registration style (no
decorator magic/auto-discovery), but deliberately skips its priority-
ordered fallback-between-adapters machinery: Observers are one-per-source
with no overlap, so this is closer to runtime/executor.py's flat ACTIONS
dispatch table than to CapabilityRegistry's adapter resolution.
"""

from __future__ import annotations

from runtime.observers.base import Observer, ObserverError


class ObserverRegistry:
    def __init__(self) -> None:
        self._observers: dict[str, Observer] = {}

    def register(self, observer: Observer) -> None:
        self._observers[observer.source] = observer

    def get(self, source: str) -> Observer:
        try:
            return self._observers[source]
        except KeyError:
            raise ObserverError(f"Unknown observer: {source!r}") from None

    def all(self) -> list[Observer]:
        return list(self._observers.values())

    def names(self) -> list[str]:
        return list(self._observers.keys())


def _default_observers() -> list[Observer]:
    # yfinance/pandas are API-tier deps (requirements-api.txt), absent on the
    # core tier (requirements-core.txt — Android/Termux, zero compilation).
    # Degrade to an empty registry there instead of crashing at import time.
    try:
        from runtime.observers.market_observers import default_yfinance_observers
    except ImportError:
        return []

    return default_yfinance_observers()


registry = ObserverRegistry()
for _observer in _default_observers():
    registry.register(_observer)
