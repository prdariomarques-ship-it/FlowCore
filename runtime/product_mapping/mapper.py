"""Layer 4 of the SCPX Impact architecture -- Product Mapping.

Converts a generic Recommendation Engine action_key (Layer 3, runtime/
impact/recommendations.py -- "reduce_duration", "increase_usd_liquidity",
...) into concrete, shelf-specific products. Completely configurable via
JSON files under config/product_shelves/ -- NEVER hardcoded inside the
Impact Engine or Recommendation Engine, which only ever emit generic
action_keys and stay entirely ignorant of this module.

The same action_key maps to different concrete products depending on the
shelf selected (US ETFs, Brazilian renda fixa, a private bank's own
shelf, ...) without any change to the engine that produced the
recommendation -- add a new shelf by dropping a new JSON file here, no
code change required.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

__all__ = ["ProductMappingError", "DEFAULT_SHELF", "list_shelves", "load_shelf", "map_action"]

SHELF_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "product_shelves"
DEFAULT_SHELF = "us_etf"


class ProductMappingError(RuntimeError):
    """Raised for an unknown product shelf."""


@lru_cache(maxsize=None)
def load_shelf(shelf: str) -> dict:
    """Loads and validates a shelf exists. Cached per shelf name for the
    life of the process -- shelf config is read at first use, same as
    config/loader.py's file-based config. Raises ProductMappingError for
    an unknown shelf (never silently falls back to a default)."""
    path = SHELF_DIR / f"{shelf}.json"
    if not path.exists():
        raise ProductMappingError(f"Unknown product shelf: {shelf!r}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_shelves() -> list[str]:
    if not SHELF_DIR.exists():
        return []
    return sorted(p.stem for p in SHELF_DIR.glob("*.json"))


def map_action(action_key: str, shelf: str = DEFAULT_SHELF) -> list[dict]:
    """Returns the shelf's configured products for this action_key, or an
    empty list if the shelf simply has nothing mapped for it -- never
    fabricated, same insufficient-data-over-fabrication discipline as
    every other SCPX engine."""
    data = load_shelf(shelf)
    return data.get("products", {}).get(action_key, [])
