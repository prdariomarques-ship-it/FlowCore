"""Dimension → source mapping.

Explicit list, mirroring runtime/observers/registry.py's
_default_observers() style (no auto-discovery). Only dimensions with real
Observer coverage today — Inflação/Crescimento/Crédito/Fiscal/Geopolítica
have no source feeding them yet and are deliberately absent rather than
scored from nothing. Adding a new dimension, or moving a source between
dimensions, is a one-line change here — no other file needs to change.
"""

from __future__ import annotations

DIMENSIONS: dict[str, list[str]] = {
    "commodities": ["oil", "gold"],
    "liquidity": ["treasury", "dollar"],
    "risk_sentiment": ["vix"],
}
