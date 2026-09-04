"""Canonical schema for Asset's manually-tagged soft attributes.

Single source of truth for which "soft" classification fields exist.
storage/portfolio_repo.py's `attributes` JSON column can technically hold
any key, but every public interface (API, CLI, MCP) derives its accepted
field list from here — add a new attribute in exactly one place, not
three (or four). Stdlib-only, deliberately: every layer that needs this
list (including flowcore.py's core-tier CLI) must be able to import it
without requirements-api.txt installed.
"""

from __future__ import annotations

ASSET_ATTRIBUTE_FIELDS: tuple[str, ...] = (
    "theme",
    "duration",
    "credit_quality",
    "liquidity",
    "income_generation",
    "inflation_protection",
    "currency_protection",
    "risk_attributes",
    "region",
    "interest_rate_sensitivity",
    "growth_profile",
    "correlation_group",
)
