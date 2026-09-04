"""FlowCore — SCPX Exposure Engine (Sprint 22, Phase 2 of the Wealth Copilot vision).

Pure computation over already-fetched, already-valued holdings — no
network calls, core-tier, no new dependency. Deterministic, explainable
weighted classification breakdowns (asset_class/sector/industry/country/
currency/any canonical soft attribute) plus concentration (HHI, top-N
weight). No LLM, no correlation, no macro-exposure mapping — see
engine.py's module docstring for why those are deliberately out of scope
this phase.
"""

from __future__ import annotations

from runtime.exposure.bucket import ConcentrationReport, ExposureBucket, ExposureReport
from runtime.exposure.engine import ExposureEngine, ExposureError, compute_concentration

__all__ = [
    "ConcentrationReport",
    "ExposureBucket",
    "ExposureEngine",
    "ExposureError",
    "ExposureReport",
    "compute_concentration",
]
