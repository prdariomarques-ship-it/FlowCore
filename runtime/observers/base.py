"""Observer ABC — Single Responsibility: observers only observe.

Forbidden inside any Observer implementation: interpreting markets,
generating recommendations, scoring assets, analyzing portfolios, or
emitting notifications. Observers must never call each other.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from runtime.observers.event import MarketEvent


class ObserverError(RuntimeError):
    """Raised when an observer fails to produce an event (fetch, timeout, etc.)."""


class Observer(ABC):
    source: str
    category: str

    @abstractmethod
    def observe(self) -> list[MarketEvent]:
        """Fetch and return this observer's current MarketEvent(s)."""
