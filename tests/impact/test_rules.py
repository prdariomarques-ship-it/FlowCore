"""Sanity checks on the deterministic rule table (Sprint 23).

Core tier — pure data, no network.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestRulesTable:
    def test_covers_exactly_the_regime_engine_dimensions(self):
        from runtime.impact.rules import RULES
        from runtime.macro_score import DIMENSIONS

        assert set(RULES.keys()) == set(DIMENSIONS.keys())

    def test_every_rule_has_both_driver_labels_and_reasons(self):
        from runtime.impact.rules import RULES

        for dim, rule in RULES.items():
            assert rule.dimension == dim
            assert rule.driver_when_elevated
            assert rule.driver_when_depressed
            assert rule.reason_when_elevated
            assert rule.reason_when_depressed

    def test_no_sector_is_both_positive_and_negative_within_a_rule(self):
        from runtime.impact.rules import RULES

        for rule in RULES.values():
            assert not (rule.positive_sectors_when_elevated & rule.negative_sectors_when_elevated)

    def test_no_asset_class_is_both_positive_and_negative_within_a_rule(self):
        from runtime.impact.rules import RULES

        for rule in RULES.values():
            assert not (rule.positive_asset_classes_when_elevated & rule.negative_asset_classes_when_elevated)

    def test_rules_never_reference_a_specific_ticker_or_product(self):
        """Architectural boundary (corrected mid-Sprint-23): the Impact
        Engine must classify by category only (sector/asset_class/
        country/soft attribute), never by a specific ticker or fund —
        that's runtime/product_mapping/'s job. DriverRule simply has no
        field capable of holding a symbol allowlist any more; this test
        pins that shape so it can't silently regress."""
        from dataclasses import fields

        from runtime.impact.rules import DriverRule

        field_names = {f.name for f in fields(DriverRule)}
        assert not any("symbol" in name for name in field_names)

    def test_soft_attribute_when_set_is_a_canonical_field(self):
        from runtime.impact.rules import RULES
        from runtime.portfolio.attributes import ASSET_ATTRIBUTE_FIELDS

        for rule in RULES.values():
            if rule.soft_attribute:
                assert rule.soft_attribute in ASSET_ATTRIBUTE_FIELDS
