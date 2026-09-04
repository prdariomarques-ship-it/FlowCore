"""FlowCore -- SCPX Decision Engine (Sprint 24, Layer 5).

The stage after Product Mapping in the SCPX pipeline: Observer ->
Macro Score -> Regime -> Exposure -> Portfolio Impact -> Recommendation
-> Product Mapping -> Decision (this package). Transforms the generic,
product-agnostic recommendations from Layer 3 into an ordered decision
queue with priority, urgency, confidence, and a fully explicit reason
chain -- "what should I do first," not just "what happened."

No LLM, no prompts anywhere in this package. Every number is either
copied from an upstream engine or a documented, deterministic
combination of them (runtime/decision/priority.py, confidence.py,
urgency.py, materiality.py). Product Mapping (Layer 4) remains the only
layer allowed to know concrete tickers/funds -- this package only ever
calls runtime.product_mapping.map_action(), never hardcodes a product.

Deliberately core-tier: composes ImpactEngine/ExposureEngine (themselves
core-tier) and runtime/product_mapping/ (pure JSON reads) -- no network
calls, no new dependency.
"""

from __future__ import annotations

from runtime.decision.engine import DecisionEngine
from runtime.decision.models import Decision, DecisionReport, PortfolioScore, SubScore

__all__ = ["Decision", "DecisionEngine", "DecisionReport", "PortfolioScore", "SubScore"]
