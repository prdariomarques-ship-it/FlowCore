"""Tests for runtime.market_intelligence.market_close and
market_close_card — the "Prepare o fechamento de mercado" pipeline:
busca os dados -> interpreta -> monta o texto (cliente + Instagram) ->
cria o card -> salva tudo organizado.

build_briefing()'s network calls are mocked throughout — no real
yfinance/BCB calls.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _fake_curve():
    from runtime.market_intelligence.yield_curve import CurvePoint, YieldCurve
    return YieldCurve(
        points=[CurvePoint("treasury", "10Y", 4.2, 4.1)],
        slope_10y_2y=10, slope_30y_10y=5, previous_slope_10y_2y=8,
        state="normal", shape="bull-steepening", interpretation="teste",
    )


def _fake_fx():
    return {"dxy_delta_pct_1d": 0.3, "pairs": [
        {"name": "USD/BRL", "level": 5.21, "delta_pct_1d": -0.2, "usd_regime": "strengthening"},
    ]}


def _fake_classes():
    return {"classes": {"equities": {
        "name": "Bolsas", "sources": [{"source": "ibovespa", "delta": 1.5, "delta_unit": "pct"}],
    }}}


@pytest.fixture
def mocked_briefing():
    from runtime.market_intelligence import briefing
    with (
        patch.object(briefing, "build_yield_curve", _fake_curve),
        patch.object(briefing, "analyze_fx", _fake_fx),
        patch.object(briefing, "analyze_asset_classes", _fake_classes),
    ):
        yield


class TestBuildMarketClose:
    def test_produces_both_text_versions_and_persists(self, mocked_briefing, tmp_path):
        from runtime.market_intelligence import market_close

        with patch.object(market_close, "_HISTORY_DIR", tmp_path):
            package = market_close.build_market_close()

        assert "FECHAMENTO DE MERCADO" in package["client_version"]
        assert "Fechamento de mercado" in package["instagram_version"]
        assert len(package["instagram_version"]) <= 2200
        assert package["saved_to"] is not None
        assert Path(package["saved_to"]).exists()
        persisted = json.loads(Path(package["saved_to"]).read_text())
        assert persisted["generated_at"] == package["generated_at"]

    def test_instagram_version_never_exceeds_caption_limit_with_many_lines(self, tmp_path):
        from runtime.market_intelligence import market_close

        many_lines = [f"LINHA {i}: destaque de teste bem longo para forçar corte" for i in range(50)]
        with patch.object(market_close, "build_briefing", lambda: {
            "lines": many_lines, "generated_at": "2026-09-05T20:00:00+00:00",
        }):
            package = market_close.build_market_close()

        assert len(package["instagram_version"]) <= 2200

    def test_card_is_generated_and_saved_as_png(self, mocked_briefing, tmp_path):
        pytest.importorskip("PIL")
        from runtime.market_intelligence import market_close

        with patch.object(market_close, "_HISTORY_DIR", tmp_path):
            package = market_close.build_market_close()

        assert package["card_path"] is not None
        card_path = Path(package["card_path"])
        assert card_path.exists()
        assert card_path.suffix == ".png"
        assert card_path.stat().st_size > 0

    def test_missing_data_degrades_honestly_without_crashing(self, tmp_path):
        from runtime.market_intelligence import market_close

        with patch.object(market_close, "build_briefing", lambda: {
            "lines": [], "generated_at": "2026-09-05T20:00:00+00:00",
        }):
            with patch.object(market_close, "_HISTORY_DIR", tmp_path):
                package = market_close.build_market_close()  # must not raise

        assert "Sem dados" in package["client_version"]
        assert "Sem dados" in package["instagram_version"]


class TestRenderCloseCard:
    def test_renders_png_with_wrapped_and_filtered_lines(self, tmp_path):
        pytest.importorskip("PIL")
        from runtime.market_intelligence.market_close_card import render_close_card

        lines = [
            "CURVA EUA: normal (10Y-2Y 10 bps)",
            "REGIME: commodities=depressed | liquidity=neutral",  # must be filtered out
            "DÓLAR: DXY +0.30% no dia",
        ]
        out = tmp_path / "card.png"
        result = render_close_card(lines, "2026-09-05T20:00:00+00:00", out)

        assert result == str(out)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_handles_empty_lines_without_crashing(self, tmp_path):
        pytest.importorskip("PIL")
        from runtime.market_intelligence.market_close_card import render_close_card

        out = tmp_path / "card.png"
        render_close_card([], "2026-09-05T20:00:00+00:00", out)  # must not raise

        assert out.exists()
