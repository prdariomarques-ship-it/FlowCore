"""Tests for runtime.product_mapping.mapper (Sprint 23, Layer 4).

Core tier — pure JSON file reads, no network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestListShelves:
    def test_includes_the_shipped_reference_shelves(self):
        from runtime.product_mapping import list_shelves

        shelves = list_shelves()
        assert "us_etf" in shelves
        assert "br_renda_fixa" in shelves


class TestLoadShelf:
    def test_loads_known_shelf(self):
        from runtime.product_mapping import load_shelf

        data = load_shelf("us_etf")
        assert "products" in data

    def test_unknown_shelf_raises(self):
        from runtime.product_mapping import ProductMappingError, load_shelf

        with pytest.raises(ProductMappingError, match="Unknown product shelf"):
            load_shelf("not_a_real_shelf")


class TestMapAction:
    def test_known_action_key_returns_products(self):
        from runtime.product_mapping import map_action

        products = map_action("reduce_duration", "us_etf")
        assert len(products) > 0
        for p in products:
            assert "symbol" in p
            assert "name" in p

    def test_unknown_action_key_returns_empty_list_not_error(self):
        from runtime.product_mapping import map_action

        assert map_action("not_a_real_action", "us_etf") == []

    def test_same_action_key_maps_to_different_products_per_shelf(self):
        from runtime.product_mapping import map_action

        us = {p["symbol"] for p in map_action("increase_inflation_protection", "us_etf")}
        br = {p["symbol"] for p in map_action("increase_inflation_protection", "br_renda_fixa")}
        assert us
        assert br
        assert us != br

    def test_default_shelf_is_us_etf(self):
        from runtime.product_mapping import DEFAULT_SHELF

        assert DEFAULT_SHELF == "us_etf"

    def test_unknown_shelf_raises_not_silent_empty(self):
        from runtime.product_mapping import ProductMappingError, map_action

        with pytest.raises(ProductMappingError):
            map_action("reduce_duration", "bogus_shelf")


class TestShelfFilesAreWellFormed:
    """Every action_key referenced by the Recommendation Engine should be
    mappable on the two shipped reference shelves — catches a shelf JSON
    silently missing an action_key added later to recommendations.py."""

    def test_every_recommendation_action_key_is_covered_by_shipped_shelves(self):
        from runtime.impact.recommendations import _ACTION_FOR_NEGATIVE_DRIVER, _ACTION_FOR_POSITIVE_DRIVER
        from runtime.product_mapping import list_shelves, load_shelf

        expected_keys = {key for key, _ in _ACTION_FOR_NEGATIVE_DRIVER.values()}
        expected_keys |= {key for key, _ in _ACTION_FOR_POSITIVE_DRIVER.values()}
        expected_keys.add("reduce_concentration")

        for shelf in list_shelves():
            data = load_shelf(shelf)
            configured_keys = set(data.get("products", {}).keys())
            missing = expected_keys - configured_keys
            assert not missing, f"shelf {shelf!r} is missing products for: {missing}"
