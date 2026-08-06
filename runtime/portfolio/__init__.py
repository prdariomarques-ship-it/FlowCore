"""FlowCore — Portfolio Domain runtime (Sprint 21, Phase 1).

Three single-purpose pieces, composed by service.py (not by each other):
- attributes.py: ASSET_ATTRIBUTE_FIELDS — the canonical, dependency-free
  schema of manually-tagged soft attributes. Every public interface (API,
  CLI, MCP) derives its accepted field list from here.
- asset_provider.py: fetch_asset_info(symbol) — yfinance-backed
  classification enrichment (name/sector/industry/country/currency/
  asset_class), used once per new symbol to populate storage's assets
  table.
- valuation.py: value_holding()/value_holdings() — live market value,
  computed fresh on every read, never persisted.

Deliberately re-exports only attributes.py's dependency-free name —
asset_provider.py/valuation.py need yfinance, so importing this package's
__init__ must never require an optional dependency to be installed (same
"optional dependency behind a local import" fix already applied to
runtime/observers/__init__.py). Callers needing fetch_asset_info/
value_holding(s) import them directly from their submodules.
"""

from __future__ import annotations

from runtime.portfolio.attributes import ASSET_ATTRIBUTE_FIELDS

__all__ = ["ASSET_ATTRIBUTE_FIELDS"]
