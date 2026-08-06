"""FlowCore -- SCPX Portfolio Impact Engine (Sprint 23, Phase 3 of the Wealth Copilot vision).

The first stage that connects Market -> Macro Scores -> Regime ->
Portfolio: translates the current macro regime (Sprint 20) into expected
impacts on a specific portfolio's actual holdings (Sprint 21 Portfolio
Domain + Sprint 22 Exposure/Concentration). No LLM, no prompts, no AI
providers -- only explainable, deterministic rules (runtime/impact/
rules.py) evaluated against real classification data (runtime/impact/
scenarios.py) and composed into one ImpactReport (runtime/impact/
engine.py), including deterministic recommendations/opportunities
(runtime/impact/recommendations.py).

Deliberately core-tier: composes RegimeEngine (itself core-tier, reads
only persisted MarketEvent history) and ExposureEngine's
compute_concentration() -- no network calls, no new dependency.
"""

from __future__ import annotations

from runtime.impact.engine import ImpactEngine
from runtime.impact.models import DriverImpact, ImpactBucket, ImpactReport, Recommendation
from runtime.impact.scenarios import ImpactError

__all__ = [
    "DriverImpact",
    "ImpactBucket",
    "ImpactEngine",
    "ImpactError",
    "ImpactReport",
    "Recommendation",
]
