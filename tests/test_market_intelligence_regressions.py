"""Regression tests for a chain of silent bugs found while wiring the
regime signal into the daily briefing:

1. build_yield_curve()'s "insufficient data" branch constructed
   YieldCurve without shape/interpretation, both required fields —
   crashed with TypeError on any network hiccup instead of degrading.
2. build_briefing() / brief_diario._section_regime() called
   RegimeEngine().classify_all() with no arguments and no await —
   RegimeEngine requires a MacroScoreEngine, and classify_all() is a
   coroutine function. Both call sites wrapped this in a bare
   `except Exception: ...`, so the resulting TypeError was swallowed
   and the regime section was always silently empty/unavailable.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestYieldCurveInsufficientData:
    def test_does_not_raise_when_fewer_than_two_yields_available(self):
        from runtime.market_intelligence.yield_curve import build_yield_curve

        with patch("runtime.market_intelligence.yield_curve._fetch", return_value={}):
            curve = build_yield_curve()  # must not raise

        assert curve.state == "insufficient_data"
        assert curve.shape is None
        assert curve.interpretation is None

    def test_to_dict_is_json_serialisable(self):
        import json
        from runtime.market_intelligence.yield_curve import build_yield_curve

        with patch("runtime.market_intelligence.yield_curve._fetch", return_value={}):
            curve = build_yield_curve()

        json.dumps(curve.to_dict())  # must not raise


class TestRegimeEngineConstruction:
    def test_classify_all_runs_end_to_end_via_run_sync(self, tmp_path):
        """The construction pattern build_briefing()/brief_diario use:
        RegimeEngine(MacroScoreEngine(EventRepository())), driven through
        run_sync() since classify_all() is async but these call sites are
        sync. Must return real RegimeSignal objects, never raise."""
        from runtime.asyncio_utils import run_sync
        from runtime.macro_score.engine import MacroScoreEngine
        from runtime.regime.engine import RegimeEngine
        from storage import EventRepository

        repo = EventRepository(db_path=str(tmp_path / "events.db"))
        engine = RegimeEngine(MacroScoreEngine(repo))
        signals = run_sync(engine.classify_all())

        assert len(signals) > 0
        for s in signals:
            assert s.dimension
            assert s.regime in ("elevated", "depressed", "neutral", "insufficient_data")


class TestBriefingRegimeSection:
    def test_build_briefing_includes_regime_line_without_crashing(self):
        from runtime.market_intelligence import briefing
        from runtime.market_intelligence.yield_curve import CurvePoint, YieldCurve

        fake_curve = YieldCurve(
            points=[CurvePoint("treasury", "10Y", 4.2, 4.1)],
            slope_10y_2y=10, slope_30y_10y=5, previous_slope_10y_2y=8,
            state="normal", shape="bull-steepening", interpretation="teste",
        )

        with (
            patch.object(briefing, "build_yield_curve", lambda: fake_curve),
            patch.object(briefing, "analyze_fx", lambda: {"dxy_delta_pct_1d": 0.3, "pairs": []}),
            patch.object(briefing, "analyze_asset_classes", lambda: {"classes": {}}),
        ):
            result = briefing.build_briefing()  # must not raise

        assert any(line.startswith("REGIME:") for line in result["lines"])


class TestBriefDiarioRegimeSection:
    def test_section_regime_reports_ok_with_real_signals(self):
        from runtime.ai.brief_diario import _section_regime

        result = _section_regime()

        assert result["ok"] is True
        assert len(result["signals"]) > 0
        assert all("name" in s and "status" in s for s in result["signals"])
