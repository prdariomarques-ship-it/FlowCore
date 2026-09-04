"""FlowCore -- SCPX Narrative Engine (Sprint 25).

The presentation layer over an already-computed DecisionReport (Layer 5)
-- translates the deterministic decision queue into readable prose via
the existing local Ollama integration (runtime/ollama.py, same one
service.ask()/the Chat tab already use). This is the ONLY place in the
whole SCPX pipeline an LLM is ever called, and strictly downstream:
nothing here feeds back into Regime/Exposure/Impact/Recommendation/
Product Mapping/Decision. Degrades to a deterministic, LLM-free fallback
narrative (built from the same reason chains) if Ollama is unavailable
-- the feature always works, the LLM is a strict enhancement, never a
dependency.

Deliberately core-tier: runtime/ollama.py is stdlib-only (urllib, no
requests/yfinance), so this package imports cleanly with only
requirements-core.txt installed -- no network call happens at import
time, and calling generate() without Ollama running simply falls back.
"""

from __future__ import annotations

from runtime.narrative.engine import NarrativeEngine
from runtime.narrative.models import NarrativeReport

__all__ = ["NarrativeEngine", "NarrativeReport"]
