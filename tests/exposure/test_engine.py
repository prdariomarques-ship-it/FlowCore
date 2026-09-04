"""Tests for runtime.exposure.engine.ExposureEngine/compute_concentration.

Core tier — pure computation over plain dicts, no network, no
optional-dependency guard needed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _holding(symbol, market_value, **asset_fields):
    asset = None
    if market_value is not None:
        asset = {
            "asset_class": asset_fields.get("asset_class"),
            "sector": asset_fields.get("sector"),
            "industry": asset_fields.get("industry"),
            "country": asset_fields.get("country"),
            "currency": asset_fields.get("currency"),
            "attributes": asset_fields.get("attributes", {}),
        }
    return {"symbol": symbol, "market_value": market_value, "asset": asset}


class TestCompute:
    def test_groups_and_weights_correctly(self):
        from runtime.exposure import ExposureEngine

        holdings = [
            _holding("AAPL", 3000.0, sector="Technology"),
            _holding("MSFT", 2000.0, sector="Technology"),
            _holding("PBR", 1000.0, sector="Energy"),
        ]
        report = ExposureEngine().by_sector(holdings)
        assert report.total_market_value == 6000.0
        assert report.unvalued_count == 0
        tech = next(b for b in report.buckets if b.label == "Technology")
        energy = next(b for b in report.buckets if b.label == "Energy")
        assert tech.weight_pct == pytest.approx(83.333, rel=1e-3)
        assert tech.holding_count == 2
        assert set(tech.symbols) == {"AAPL", "MSFT"}
        assert energy.weight_pct == pytest.approx(16.667, rel=1e-3)

    def test_buckets_sorted_by_weight_descending(self):
        from runtime.exposure import ExposureEngine

        holdings = [
            _holding("A", 100.0, sector="Small"),
            _holding("B", 900.0, sector="Big"),
        ]
        report = ExposureEngine().by_sector(holdings)
        assert [b.label for b in report.buckets] == ["Big", "Small"]

    def test_missing_classification_is_unclassified_not_dropped(self):
        from runtime.exposure import ExposureEngine

        holdings = [_holding("AAPL", 1000.0, sector=None)]
        report = ExposureEngine().by_sector(holdings)
        assert len(report.buckets) == 1
        assert report.buckets[0].label == "Unclassified"
        assert report.buckets[0].weight_pct == 100.0

    def test_unvalued_holding_excluded_from_weights_but_counted(self):
        from runtime.exposure import ExposureEngine

        holdings = [
            _holding("AAPL", 1000.0, sector="Technology"),
            _holding("BOGUS", None),
        ]
        report = ExposureEngine().by_sector(holdings)
        assert report.total_market_value == 1000.0
        assert report.unvalued_count == 1
        assert sum(b.holding_count for b in report.buckets) == 1

    def test_empty_holdings_returns_empty_report(self):
        from runtime.exposure import ExposureEngine

        report = ExposureEngine().by_sector([])
        assert report.buckets == []
        assert report.total_market_value == 0.0
        assert report.unvalued_count == 0

    def test_all_unvalued_gives_zero_total_no_division_error(self):
        from runtime.exposure import ExposureEngine

        holdings = [_holding("A", None), _holding("B", None)]
        report = ExposureEngine().by_sector(holdings)
        assert report.total_market_value == 0.0
        assert report.unvalued_count == 2
        assert report.buckets == []


class TestHardDimensions:
    def test_asset_class_sector_industry_country_currency(self):
        from runtime.exposure import ExposureEngine

        holdings = [
            _holding(
                "AAPL",
                1000.0,
                asset_class="equity",
                sector="Technology",
                industry="Consumer Electronics",
                country="United States",
                currency="USD",
            )
        ]
        engine = ExposureEngine()
        assert engine.by_asset_class(holdings).buckets[0].label == "equity"
        assert engine.by_sector(holdings).buckets[0].label == "Technology"
        assert engine.by_industry(holdings).buckets[0].label == "Consumer Electronics"
        assert engine.by_country(holdings).buckets[0].label == "United States"
        assert engine.by_currency(holdings).buckets[0].label == "USD"

    def test_full_report_covers_all_hard_dimensions(self):
        from runtime.exposure import ExposureEngine

        holdings = [_holding("AAPL", 1000.0, sector="Technology")]
        full = ExposureEngine().full_report(holdings)
        assert set(full.keys()) == {"asset_class", "sector", "industry", "country", "currency"}


class TestSoftAttributes:
    def test_by_attribute_reads_from_attributes_dict(self):
        from runtime.exposure import ExposureEngine

        holdings = [_holding("AAPL", 1000.0, attributes={"theme": "AI"})]
        report = ExposureEngine().by_attribute(holdings, "theme")
        assert report.buckets[0].label == "AI"

    def test_by_attribute_unknown_field_raises(self):
        from runtime.exposure import ExposureEngine, ExposureError

        with pytest.raises(ExposureError, match="Unknown attribute"):
            ExposureEngine().by_attribute([], "not_a_real_field")


class TestByDimension:
    def test_dispatches_hard_dimension(self):
        from runtime.exposure import ExposureEngine

        holdings = [_holding("AAPL", 1000.0, sector="Technology")]
        report = ExposureEngine().by_dimension(holdings, "sector")
        assert report.dimension == "sector"

    def test_dispatches_soft_attribute(self):
        from runtime.exposure import ExposureEngine

        holdings = [_holding("AAPL", 1000.0, attributes={"theme": "AI"})]
        report = ExposureEngine().by_dimension(holdings, "theme")
        assert report.dimension == "theme"

    def test_unknown_dimension_raises(self):
        from runtime.exposure import ExposureEngine, ExposureError

        with pytest.raises(ExposureError, match="Unknown exposure dimension"):
            ExposureEngine().by_dimension([], "bogus")


class TestConcentration:
    def test_single_holding_is_fully_concentrated(self):
        from runtime.exposure import compute_concentration

        report = compute_concentration([_holding("AAPL", 1000.0)])
        assert report.top_holding_weight_pct == 100.0
        assert report.top_5_weight_pct == 100.0
        assert report.hhi == pytest.approx(10000.0)

    def test_equal_weights_hhi(self):
        """4 equal holdings of 25% each: HHI = 4 * 25^2 = 2500."""
        from runtime.exposure import compute_concentration

        holdings = [_holding(f"H{i}", 100.0) for i in range(4)]
        report = compute_concentration(holdings)
        assert report.hhi == pytest.approx(2500.0)
        assert report.top_5_weight_pct == 100.0

    def test_top_5_caps_at_five_holdings(self):
        from runtime.exposure import compute_concentration

        holdings = [_holding(f"H{i}", 100.0) for i in range(10)]
        report = compute_concentration(holdings)
        assert report.top_5_weight_pct == pytest.approx(50.0)  # 5 of 10 equal holdings

    def test_no_valued_holdings_returns_zeroed_report(self):
        from runtime.exposure import compute_concentration

        report = compute_concentration([_holding("A", None)])
        assert report.total_market_value == 0.0
        assert report.hhi == 0.0
        assert report.unvalued_count == 1

    def test_empty_holdings(self):
        from runtime.exposure import compute_concentration

        report = compute_concentration([])
        assert report.holding_count == 0
        assert report.hhi == 0.0
