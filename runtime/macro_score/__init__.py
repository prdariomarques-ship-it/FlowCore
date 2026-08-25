"""FlowCore — SCPX Macro Score Engine (Sprint 19).

The "Macro Score Engine" stage of the SCPX pipeline (FLOWCORE_CONSTITUTION.md,
"SCPX Vision"). Reads persisted MarketEvents (Sprint 18's Observer layer +
Sprint 19's EventRepository) and computes deterministic, explainable
per-dimension scores. No LLM, no interpretation beyond arithmetic — "AI
Philosophy": LLMs are language layers, decision engines belong to FlowCore.

Deliberately core-tier: no network access, no yfinance import anywhere in
this package — only reads what's already been persisted.
"""

from __future__ import annotations

from runtime.macro_score.dimension import DIMENSIONS
from runtime.macro_score.engine import MacroScoreEngine, MacroScoreError
from runtime.macro_score.score import DimensionScore

__all__ = ["DIMENSIONS", "DimensionScore", "MacroScoreEngine", "MacroScoreError"]
