"""FlowCore — Portfolio Domain runtime (Sprint 21, Phase 1).

Two single-purpose pieces, composed by service.py (not by each other):
- asset_provider.py: fetch_asset_info(symbol) — yfinance-backed
  classification enrichment (name/sector/industry/country/currency/
  asset_class), used once per new symbol to populate storage's assets
  table.
- valuation.py: value_holding()/value_holdings() — live market value,
  computed fresh on every read, never persisted.

Both are optional-dependency (yfinance) tier, same as runtime/observers/.
"""

from __future__ import annotations

from runtime.portfolio.asset_provider import AssetProviderError, fetch_asset_info
from runtime.portfolio.valuation import value_holding, value_holdings

__all__ = ["AssetProviderError", "fetch_asset_info", "value_holding", "value_holdings"]
