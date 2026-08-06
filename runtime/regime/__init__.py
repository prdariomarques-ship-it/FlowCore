"""FlowCore — SCPX Regime Engine (Sprint 20).

The stage immediately after Macro Score Engine in the SCPX pipeline
(FLOWCORE_CONSTITUTION.md, "SCPX Vision"). Deterministic threshold
classification of per-dimension z-scores into elevated/depressed/neutral
— no LLM, no fabricated composite "master regime". Core-tier: no network
access, composes MacroScoreEngine which itself only reads persisted
history.
"""

from __future__ import annotations

from runtime.regime.engine import DEFAULT_THRESHOLD, RegimeEngine
from runtime.regime.signal import RegimeSignal

__all__ = ["DEFAULT_THRESHOLD", "RegimeEngine", "RegimeSignal"]
