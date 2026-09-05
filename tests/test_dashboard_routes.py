"""Tests for Dashboard v4 API routes (api/dashboard_routes.py)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

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


def test_route_models_are_module_level_for_fastapi_annotation_resolution():
    """Python 3.13 resolves endpoint annotations after route registration."""
    import api.dashboard_routes as dashboard_routes
    assert dashboard_routes.TTSRequest.__module__ == "api.dashboard_routes"
    assert dashboard_routes.SMSSendRequest.__module__ == "api.dashboard_routes"
    client = _client()
    assert client.get("/api/health").status_code == 200


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


# ── _tcp_reachable — fast-fail probe used before AI provider calls ────────────

class TestTcpReachable:
    def test_unreachable_host_returns_false_fast(self):
        import time
        from api.dashboard_routes import _tcp_reachable

        start = time.monotonic()
        # TEST-NET-1 (RFC 5737): reserved, unroutable, guaranteed nothing listens.
        result = _tcp_reachable("http://192.0.2.1:11434", timeout=1.0)
        elapsed = time.monotonic() - start

        assert result is False
        assert elapsed < 2.0

    def test_no_hostname_returns_false(self):
        from api.dashboard_routes import _tcp_reachable
        assert _tcp_reachable("not-a-url", timeout=1.0) is False

    def test_reachable_host_returns_true(self):
        import socket
        import threading
        from api.dashboard_routes import _tcp_reachable

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        threading.Thread(target=server.accept, daemon=True).start()
        try:
            assert _tcp_reachable(f"http://127.0.0.1:{port}", timeout=1.0) is True
        finally:
            server.close()


class TestAskSkipsUnreachableEndpoints:
    """Regression test: chat used to hang up to ~4.5 min (90s + 180s) before
    reporting "unavailable" when the configured PC/phone Ollama wasn't up —
    this made the chat look permanently broken instead of failing fast."""

    def test_ollama_candidate_skipped_when_unreachable(self, tmp_path, monkeypatch):
        import api.dashboard_routes as dr
        monkeypatch.setattr(dr, "_DATA_DIR", tmp_path / ".flowcore")
        (tmp_path / ".flowcore").mkdir(parents=True)
        (tmp_path / ".flowcore" / "ai.json").write_text(
            json.dumps({"ollama_url": "http://10.255.255.1:11434"})
        )

        with patch("api.dashboard_routes._tcp_reachable", return_value=False) as mocked_reachable:
            with patch("api.dashboard_routes._http_json") as mocked_http:
                r = _client().post("/api/ask", json={"question": "oi"})

        assert r.status_code == 200
        assert r.json()["provider"] == "unavailable"
        mocked_reachable.assert_called()
        mocked_http.assert_not_called()


# ── /api/market/overview — must evaluate alerts, not just read stale ones ────

class TestMarketOverviewEvaluatesAlerts:
    """Regression test: nothing in the running app calls evaluate_alerts() on
    a schedule — /api/market/overview only ever read the (always-empty)
    persisted table, so the mobile home screen's "Alertas" card could never
    show a real breach even when one was actually happening."""

    def test_overview_calls_evaluate_alerts(self):
        with patch("runtime.market_intelligence.alerts.evaluate_alerts", return_value=[]) as mocked:
            with patch(
                "runtime.market_intelligence.source_catalog.source_snapshot",
                return_value={"official_observations": []},
            ):
                r = _client().get("/api/market/overview")
        assert r.status_code == 200
        mocked.assert_called_once()


# ── /api/ai-runtime/* ────────────────────────────────────────────────────────

class TestAIRuntimeConfig:
    def test_config_get_returns_200(self):
        r = _client().get("/api/ai-runtime/config")
        assert r.status_code == 200
        data = r.json()
        assert "ollama_url" in data
        assert "model" in data
        assert "default_url" in data

    def test_config_patch_saves_tailscale_url(self, tmp_path, monkeypatch):
        import api.dashboard_routes as dr
        monkeypatch.setattr(dr, "_DATA_DIR", tmp_path / ".flowcore")
        (tmp_path / ".flowcore").mkdir(parents=True)

        from fastapi.testclient import TestClient
        from api.router import create_app
        c = TestClient(create_app(version="test"))

        r = c.patch("/api/ai-runtime/config", json={"ollama_url": "http://100.64.0.2:11434"})
        assert r.status_code == 200
        assert r.json()["ollama_url"] == "http://100.64.0.2:11434"
        assert r.json()["saved"] is True

        r2 = c.get("/api/ai-runtime/config")
        assert r2.json()["ollama_url"] == "http://100.64.0.2:11434"

    def test_config_patch_model_only(self, tmp_path, monkeypatch):
        import api.dashboard_routes as dr
        monkeypatch.setattr(dr, "_DATA_DIR", tmp_path / ".flowcore")
        (tmp_path / ".flowcore").mkdir(parents=True)

        from fastapi.testclient import TestClient
        from api.router import create_app
        c = TestClient(create_app(version="test"))
        r = c.patch("/api/ai-runtime/config", json={"model": "qwen3:8b"})
        assert r.status_code == 200
        assert r.json()["model"] == "qwen3:8b"

    def test_config_url_trailing_slash_stripped(self, tmp_path, monkeypatch):
        import api.dashboard_routes as dr
        monkeypatch.setattr(dr, "_DATA_DIR", tmp_path / ".flowcore")
        (tmp_path / ".flowcore").mkdir(parents=True)

        from fastapi.testclient import TestClient
        from api.router import create_app
        c = TestClient(create_app(version="test"))
        r = c.patch("/api/ai-runtime/config", json={"ollama_url": "http://100.64.0.2:11434/"})
        assert r.json()["ollama_url"] == "http://100.64.0.2:11434"

    def test_config_patch_saves_openai_compatible_provider(self, tmp_path, monkeypatch):
        import api.dashboard_routes as dr
        monkeypatch.setattr(dr, "_DATA_DIR", tmp_path / ".flowcore")
        (tmp_path / ".flowcore").mkdir(parents=True)
        from fastapi.testclient import TestClient
        from api.router import create_app
        c = TestClient(create_app(version="test"))
        r = c.patch("/api/ai-runtime/config", json={
            "openai_url": "http://100.127.43.83:1234/",
            "openai_model": "nemotron-3.5-lightning",
        })
        assert r.status_code == 200
        assert r.json()["openai_url"] == "http://100.127.43.83:1234"
        assert r.json()["openai_model"] == "nemotron-3.5-lightning"


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
        assert r.json()["stub"] is False

    def test_fx_has_pairs_and_regime(self):
        data = _client().get("/api/market/fx").json()
        assert "pairs" in data
        assert "dxy_delta_pct_1d" in data

    def test_snapshot_has_real_or_explicitly_missing_values(self):
        data = _client().get("/api/market/snapshot").json()
        for field in ("brl_usd", "selic_rate", "ipca_12m", "ibov_last", "ibov_change_pct", "observations", "timestamp"):
            assert field in data
        assert data["stub"] is False
        assert set(data["observations"]).issubset({"brl_usd", "selic_rate", "ipca_12m", "ibovespa"})

    def test_yield_curve_structure(self):
        data = _client().get("/api/market/yield-curve").json()
        assert "points" in data
        assert "slope_10y_2y_bps" in data
        assert "shape" in data

    def test_news_contract_has_pagination_and_provenance(self, monkeypatch):
        import runtime.market_intelligence.news as news

        def fake_fetch(symbol):
            return [{
                "headline": f"Mercado {symbol}",
                "publisher": "Fonte de teste",
                "link": f"https://example.com/{symbol}",
                "timestamp": "2026-08-25T12:00:00+00:00",
                "related_symbol": symbol,
            }]

        monkeypatch.setattr(news, "_fetch_news", fake_fetch)
        data = _client().get("/api/market/news?section=brasil&limit=1").json()
        assert data["available"] is True
        assert data["stub"] is False
        assert data["section"] == "brasil"
        assert data["next_cursor"] == "1"
        assert len(data["items"]) == 1
        item = data["items"][0]
        for field in ("id", "headline", "publisher", "provider", "canonical_url", "published_at", "collected_at", "related_assets", "status"):
            assert field in item
        assert item["provider"]["id"] == "yahoo_finance"
        assert item["canonical_url"].startswith("https://example.com/")

    def test_news_rejects_unknown_section(self):
        response = _client().get("/api/market/news?section=desconhecida")
        assert response.status_code == 422


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
        pid = "moderate-ia-1m"
        r = _client().get(f"/api/portfolios/{pid}/{sub}")
        assert r.status_code == 200
        data = r.json()
        assert data["portfolio_id"] == pid

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
        ids = [p["id"] for p in data]
        assert "main" in ids


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
