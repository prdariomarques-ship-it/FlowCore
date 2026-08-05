"""FlowCore — SCPX Observer framework (Sprint 18).

The "Market Data" stage of the SCPX pipeline (FLOWCORE_CONSTITUTION.md,
"SCPX Vision"). Observers only observe: they fetch raw data and emit
normalized MarketEvents. They never interpret, score, or recommend —
that's the Macro Score Engine and later stages (future sprints).

Deliberately re-exports only dependency-free names (MarketEvent, Observer,
ObserverError — stdlib only). `registry`/`scheduler` pull in yfinance-
backed observers transitively, so callers import them directly from their
submodules (`from runtime.observers.registry import registry`) — the same
"optional dependency behind a local import" discipline used everywhere
else in this codebase, applied at the package level too: importing this
package's __init__ must never require an optional dependency to be
installed.
"""

from __future__ import annotations

from runtime.observers.base import Observer, ObserverError
from runtime.observers.event import MarketEvent

__all__ = [
    "MarketEvent",
    "Observer",
    "ObserverError",
]
