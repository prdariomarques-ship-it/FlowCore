"""Tests for Dashboard v4 API routes (api/dashboard_routes.py)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _client():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from api.router import create_app
    return TestClient(create_app(version="test", platform_info={"os_name": "test"}))


# ── /api/ask ─────────────────────────────────────────────────────────────────

class TestAsk:
    def test_empty_question_returns_422(self):
        r = _client().post("/api/ask", json={"question": ""})
        assert r.status_code == 422

    def test_whitespace_question_returns_422(self):
        r = _client().post("/api/ask", json={"question": "   "})
        assert r.status_code == 422

    def test_valid_question_returns_200(self):
        # Ollama won't be running in CI — expect graceful fallback
        r = _client().post("/api/ask", json={"question": "oi"})
        assert r.status_code == 200
        data = r.json()
        assert "answer" in data
        assert "provider" in data
        assert "model" in data

    def test_unavailable_provider_still_200(self):
        r = _client().post("/api/ask", json={"question": "test"})
        assert r.status_code == 200
        # provider may be "unavailable" when Ollama is absent
        assert r.json()["provider"] in ("ollama", "flowcore-agent", "unavailable")

    def test_missing_question_field_returns_422(self):
        r = _client().post("/api/ask", json={})
        assert r.status_code == 422

    def test_history_accepted(self):
        r = _client().post("/api/ask", json={
            "question": "continue",
            "history": [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}],
        })
        assert r.status_code == 200


# ── /api/ai-runtime/* ────────────────────────────────────────────────────────

class TestAIRuntime:
    def test_models_returns_200(self):
        r = _client().get("/api/ai-runtime/models")
        assert r.status_code == 200
        data = r.json()
        assert "models" in data
        assert isinstance(data["models"], list)
        assert "provider" in data

    def test_memory_returns_200(self):
        r = _client().get("/api/ai-runtime/memory")
        assert r.status_code == 200
        data = r.json()
        assert "loaded_models" in data
        assert "provider" in data
        assert "context_window" in data

    def test_load_returns_200(self):
        r = _client().post("/api/ai-runtime/load", json={"model": "llama3"})
        assert r.status_code == 200
        data = r.json()
        assert "loaded" in data
        assert data["model"] == "llama3"

    def test_unload_returns_200(self):
        r = _client().post("/api/ai-runtime/unload", json={"model": "llama3"})
        assert r.status_code == 200
        data = r.json()
        assert "unloaded" in data
        assert data["model"] == "llama3"

    def test_load_missing_model_returns_422(self):
        r = _client().post("/api/ai-runtime/load", json={})
        assert r.status_code == 422


# ── /api/market/* ─────────────────────────────────────────────────────────────

class TestMarketEndpoints:
    @pytest.mark.parametrize("path", [
        "/api/market/fx",
        "/api/market/yield-curve",
        "/api/market/rebalancing",
        "/api/market/watchlists",
        "/api/market/alerts",
        "/api/market/calendar",
        "/api/market/news",
    ])
    def test_returns_200(self, path):
        r = _client().get(path)
        assert r.status_code == 200
        assert r.json()["stub"] is True

    def test_fx_has_pairs_and_regime(self):
        data = _client().get("/api/market/fx").json()
        assert "pairs" in data
        assert "usd_regime" in data

    def test_yield_curve_structure(self):
        data = _client().get("/api/market/yield-curve").json()
        assert "points" in data
        assert "slope_10y_2y_bps" in data
        assert "shape" in data


# ── /api/macro-score/* ───────────────────────────────────────────────────────

class TestMacroScore:
    def test_current_returns_200(self):
        r = _client().get("/api/macro-score/current")
        assert r.status_code == 200
        data = r.json()
        assert "score" in data
        assert "dimensions" in data

    def test_history_returns_200(self):
        r = _client().get("/api/macro-score/history")
        assert r.status_code == 200
        assert "history" in r.json()


# ── /api/regime/signals ────────────────────────────────────────────────────────

class TestRegimeSignals:
    def test_returns_200(self):
        r = _client().get("/api/regime/signals")
        assert r.status_code == 200
        data = r.json()
        assert "regime" in data
        assert "signals" in data


# ── /api/portfolios/* ────────────────────────────────────────────────────────

class TestPortfolios:
    def test_list_returns_200(self):
        r = _client().get("/api/portfolios")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_unknown_portfolio_returns_404(self):
        r = _client().get("/api/portfolios/nonexistent_xyz")
        assert r.status_code == 404

    @pytest.mark.parametrize("sub", ["summary", "exposure", "impact", "decision", "narrative"])
    def test_sub_routes_return_200(self, sub):
        r = _client().get(f"/api/portfolios/p1/{sub}")
        assert r.status_code == 200
        data = r.json()
        assert data["portfolio_id"] == "p1"

    def test_list_reads_file(self, tmp_path, monkeypatch):
        import api.dashboard_routes as dr
        monkeypatch.setattr(dr, "_DATA_DIR", tmp_path / ".flowcore")
        cfg = tmp_path / ".flowcore"
        cfg.mkdir(parents=True)
        (cfg / "portfolios.json").write_text(json.dumps([
            {"id": "main", "name": "Principal", "assets": []}
        ]))

        from fastapi.testclient import TestClient
        from api.router import create_app
        c = TestClient(create_app(version="test"))
        r = c.get("/api/portfolios")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["id"] == "main"


# ── /api/assets/{symbol} ────────────────────────────────────────────────────

class TestAssets:
    def test_returns_200(self):
        r = _client().get("/api/assets/PETR4")
        assert r.status_code == 200
        data = r.json()
        assert data["symbol"] == "PETR4"

    def test_symbol_uppercased(self):
        r = _client().get("/api/assets/petr4")
        assert r.json()["symbol"] == "PETR4"

    def test_has_required_fields(self):
        data = _client().get("/api/assets/IBOV").json()
        for field in ("symbol", "name", "theme", "region", "income", "inflation_protection"):
            assert field in data


# ── /api/outlook/* ───────────────────────────────────────────────────────────

class TestOutlook:
    def test_auth_status_returns_200(self):
        r = _client().get("/api/outlook/auth/status")
        assert r.status_code == 200
        data = r.json()
        assert "authenticated" in data

    def test_auth_start_returns_200(self):
        r = _client().get("/api/outlook/auth/start")
        assert r.status_code == 200
        assert "auth_url" in r.json()

    def test_inbox_returns_200(self):
        r = _client().get("/api/outlook/inbox")
        assert r.status_code == 200
        data = r.json()
        assert "messages" in data
        assert "unread" in data

    def test_search_requires_q(self):
        r = _client().get("/api/outlook/search")
        assert r.status_code == 422

    def test_search_with_q(self):
        r = _client().get("/api/outlook/search?q=relatório")
        assert r.status_code == 200
        assert r.json()["query"] == "relatório"


# ── /api/calendar/* ──────────────────────────────────────────────────────────

class TestCalendar:
    @pytest.mark.parametrize("path", [
        "/api/calendar/today",
        "/api/calendar/week",
        "/api/calendar/next",
    ])
    def test_returns_200(self, path):
        r = _client().get(path)
        assert r.status_code == 200
        assert "events" in r.json() or "event" in r.json()

    def test_today_has_date(self):
        data = _client().get("/api/calendar/today").json()
        assert "date" in data

    def test_search_requires_q(self):
        r = _client().get("/api/calendar/search")
        assert r.status_code == 422

    def test_search_with_q(self):
        r = _client().get("/api/calendar/search?q=reunião")
        assert r.status_code == 200
        assert r.json()["query"] == "reunião"
