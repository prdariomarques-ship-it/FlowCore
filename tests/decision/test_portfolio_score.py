"""Tests for runtime.decision.portfolio_score (Sprint 24).

Core tier — uses a real ExposureEngine over plain dicts (no network),
mirroring tests/exposure/test_engine.py's fixture style.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _holding(symbol, market_value, **asset_fields):
    asset = None
    if market_value is not None:
        asset = {
            "asset_class": asset_fields.get("asset_class"),
            "sector": asset_fields.get("sector"),
            "country": asset_fields.get("country"),
            "attributes": asset_fields.get("attributes", {}),
        }
    return {"symbol": symbol, "market_value": market_value, "asset": asset}


def _driver(dimension, regime="elevated", positive_weight_pct=0.0):
    from runtime.impact.models import DriverImpact

    return DriverImpact(
        dimension=dimension,
        driver="d",
        regime=regime,
        regime_score=2.0 if regime != "insufficient_data" else None,
        direction="positive" if positive_weight_pct else "neutral",
        expected_impact="moderate",
        confidence_score=0.7,
        confidence_label="medium",
        exposed_weight_pct=positive_weight_pct,
        positive_weight_pct=positive_weight_pct,
        negative_weight_pct=0.0,
        reason="r",
    )


def _impact_report(drivers, portfolio_risk_score=20.0):
    from runtime.impact.models import ImpactReport

    return ImpactReport(
        portfolio_id=1,
        overall_impact="neutral",
        confidence=0.5,
        portfolio_risk_score=portfolio_risk_score,
        drivers=drivers,
        affected_dimensions=[],
        recommendations=[],
        opportunities=[],
        unvalued_count=0,
    )


def _concentration(hhi=5000.0, holding_count=2):
    from runtime.exposure import ConcentrationReport

    return ConcentrationReport(
        total_market_value=1000.0,
        top_holding_weight_pct=60.0,
        top_5_weight_pct=100.0,
        hhi=hhi,
        holding_count=holding_count,
        unvalued_count=0,
        computed_at="t",
    )


class TestComputePortfolioScore:
    def test_all_computed_when_full_data_available(self):
        from runtime.decision.portfolio_score import compute_portfolio_score
        from runtime.exposure import ExposureEngine

        holdings = [
            _holding(
                "AAPL",
                500.0,
                sector="Technology",
                attributes={"inflation_protection": "alta", "currency_protection": "alta", "liquidity": "alta"},
            ),
            _holding("XOM", 500.0, sector="Energy"),
        ]
        drivers = [_driver("liquidity", positive_weight_pct=50.0), _driver("commodities", positive_weight_pct=30.0)]
        report = compute_portfolio_score(ExposureEngine(), holdings, _impact_report(drivers), _concentration())

        by_name = {s.name: s for s in report.sub_scores}
        assert by_name["concentration"].status == "computed"
        assert by_name["diversification"].status == "computed"
        assert by_name["inflation_hedge"].status == "computed"
        assert by_name["currency_protection"].status == "computed"
        assert by_name["duration"].status == "computed"
        assert by_name["liquidity"].status == "computed"
        assert by_name["macro_alignment"].status == "computed"
        assert by_name["protection"].status == "computed"
        assert report.overall_status == "computed"
        assert report.overall is not None

    def test_untagged_no_regime_gives_insufficient_data(self):
        from runtime.decision.portfolio_score import compute_portfolio_score
        from runtime.exposure import ExposureEngine

        holdings = [_holding("AAPL", 500.0, sector="Technology")]
        drivers = [
            _driver("liquidity", regime="insufficient_data"),
            _driver("commodities", regime="insufficient_data"),
        ]
        report = compute_portfolio_score(ExposureEngine(), holdings, _impact_report(drivers), _concentration())

        by_name = {s.name: s for s in report.sub_scores}
        assert by_name["inflation_hedge"].status == "insufficient_data"
        assert by_name["inflation_hedge"].score is None
        assert by_name["currency_protection"].status == "insufficient_data"
        assert by_name["duration"].status == "insufficient_data"
        assert by_name["liquidity"].status == "insufficient_data"
        assert by_name["protection"].status == "insufficient_data"
        # concentration/diversification/macro_alignment always computable
        assert by_name["concentration"].status == "computed"
        assert by_name["macro_alignment"].status == "computed"

    def test_insufficient_data_subscores_excluded_not_zeroed_from_overall(self):
        from runtime.decision.portfolio_score import compute_portfolio_score
        from runtime.exposure import ExposureEngine

        holdings = [_holding("AAPL", 500.0, sector="Technology")]
        drivers = [_driver("liquidity", regime="insufficient_data"), _driver("commodities", regime="insufficient_data")]
        report = compute_portfolio_score(ExposureEngine(), holdings, _impact_report(drivers), _concentration())

        computed_scores = [s.score for s in report.sub_scores if s.status == "computed"]
        assert report.overall == round(sum(computed_scores) / len(computed_scores), 1)

    def test_empty_portfolio_still_returns_a_report(self):
        from runtime.decision.portfolio_score import compute_portfolio_score
        from runtime.exposure import ExposureEngine

        report = compute_portfolio_score(
            ExposureEngine(), [], _impact_report([]), _concentration(hhi=0.0, holding_count=0)
        )
        by_name = {s.name: s for s in report.sub_scores}
        assert by_name["concentration"].status == "insufficient_data"
        assert by_name["diversification"].status == "insufficient_data"

    def test_tagged_inflation_protection_takes_precedence_over_driver(self):
        from runtime.decision.portfolio_score import compute_portfolio_score
        from runtime.exposure import ExposureEngine

        holdings = [_holding("AAPL", 500.0, sector="Technology", attributes={"inflation_protection": "alta"})]
        drivers = [_driver("commodities", positive_weight_pct=10.0)]  # would give 10.0 if used
        report = compute_portfolio_score(ExposureEngine(), holdings, _impact_report(drivers), _concentration())

        by_name = {s.name: s for s in report.sub_scores}
        assert by_name["inflation_hedge"].score == 100.0  # 100% tagged, not the driver's 10.0
