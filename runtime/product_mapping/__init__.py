"""FlowCore -- Product Mapping (Sprint 23, Layer 4 of the SCPX Impact architecture).

Regime (Layer 1) -> Portfolio Impact (Layer 2) -> Recommendation (Layer 3)
-> Product Mapping (Layer 4, this package). Only this layer knows about
concrete tickers/funds/products, and only via external, swappable JSON
config (config/product_shelves/) -- never hardcoded in code, and never
imported by runtime/impact/ (that dependency only ever points this way).

Deliberately core-tier: pure JSON file reads, no network, no dependency.
"""

from __future__ import annotations

from runtime.product_mapping.mapper import DEFAULT_SHELF, ProductMappingError, list_shelves, load_shelf, map_action

__all__ = ["DEFAULT_SHELF", "ProductMappingError", "list_shelves", "load_shelf", "map_action"]
