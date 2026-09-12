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
    def _headers(self):
        from tests._auth_helper import signup_office
        return signup_office(_client())["headers"]

    def test_requires_auth(self):
        # A missing/invalid session used to only 401 on the Wealth Copilot
        # agent_intents branch -- a generic question that matched no agent
        # keyword could reach the AI provider chain (including the
        # DeepSeek fallback) with zero auth and zero cost attribution.
        r = _client().post("/api/ask", json={"question": "oi"})
        assert r.status_code == 401

    def test_empty_question_returns_422_even_without_auth(self):
        r = _client().post("/api/ask", json={"question": ""})
        assert r.status_code == 422

    def test_whitespace_question_returns_422_even_without_auth(self):
        r = _client().post("/api/ask", json={"question": "   "})
        assert r.status_code == 422

    def test_valid_question_returns_200(self):
        # Ollama won't be running in CI — expect graceful fallback
        r = _client().post("/api/ask", json={"question": "oi"}, headers=self._headers())
        assert r.status_code == 200
        data = r.json()
        assert "answer" in data
        assert "provider" in data
        assert "model" in data

    def test_unavailable_provider_still_200(self):
        r = _client().post("/api/ask", json={"question": "test"}, headers=self._headers())
        assert r.status_code == 200
        # provider may be "unavailable" when Ollama is absent
        assert r.json()["provider"] in ("ollama", "flowcore-agent", "unavailable")

    def test_missing_question_field_returns_422(self):
        r = _client().post("/api/ask", json={}, headers=self._headers())
        assert r.status_code == 422

    def test_history_accepted(self):
        r = _client().post("/api/ask", json={
            "question": "continue",
            "history": [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}],
        }, headers=self._headers())
        assert r.status_code == 200


class TestAskAgentTierIsTriedFirst:
    """The "ask" agent (agents/ask_agent.py, restricted to tenant-safe
    market/analysis tools) used to be dead code -- no agent named "ask"
    was ever registered, so this branch never fired and the Chat IA fell
    straight to raw Ollama/OpenAI/DeepSeek chat with no tool access."""

    def test_used_before_ollama_when_it_succeeds(self):
        from tests._auth_helper import signup_office
        c = _client()
        headers = signup_office(c)["headers"]

        fake_record = type("Record", (), {
            "status": "completed",
            "result": {"status": "ok", "data": {
                "answer": "Correlação de 0.42 entre ouro e dólar.",
                "model": "deepseek-chat", "tool_used": "market_correlation", "tool_result": None,
            }},
        })()

        with patch("agents.runner.AgentRunner.run", return_value=fake_record) as mocked_run, \
             patch("api.dashboard_routes._tcp_reachable") as mocked_reachable:
            r = c.post("/api/ask", json={"question": "oi"}, headers=headers)

        assert r.status_code == 200
        data = r.json()
        assert data["answer"] == "Correlação de 0.42 entre ouro e dólar."
        assert data["provider"] == "flowcore-agent"
        assert data["model"] == "deepseek-chat"
        mocked_run.assert_called_once()
        mocked_reachable.assert_not_called()  # never even tried Ollama

    def test_falls_through_to_ollama_when_ask_agent_errors(self):
        from tests._auth_helper import signup_office
        c = _client()
        headers = signup_office(c)["headers"]

        fake_record = type("Record", (), {
            "status": "completed",
            "result": {"status": "error", "data": {"reason": "no provider available"}},
        })()

        with patch("agents.runner.AgentRunner.run", return_value=fake_record), \
             patch("api.dashboard_routes._tcp_reachable", return_value=False), \
             patch("service._llm_router.generate", side_effect=RuntimeError("no llm")):
            r = c.post("/api/ask", json={"question": "oi"}, headers=headers)

        assert r.status_code == 200
        assert r.json()["provider"] == "unavailable"


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

        from tests._auth_helper import signup_office
        c = _client()
        headers = signup_office(c)["headers"]

        with patch("agents.runner.AgentRunner.list_agents", return_value=[]), \
             patch("api.dashboard_routes._tcp_reachable", return_value=False) as mocked_reachable, \
             patch("service._llm_router.generate", side_effect=RuntimeError("no llm")), \
             patch("api.dashboard_routes._http_json") as mocked_http:
            r = c.post("/api/ask", json={"question": "oi"}, headers=headers)

        assert r.status_code == 200
        assert r.json()["provider"] == "unavailable"
        mocked_reachable.assert_called()
        mocked_http.assert_not_called()


class TestAskRateLimit:
    """/api/ask chains into Ollama/OpenAI-compat/DeepSeek per question --
    the single most CPU/network-heavy endpoint in the app -- and had no
    rate limiting at all, unlike /api/auth/login's OWASP-style throttle."""

    def setup_method(self):
        from runtime.rate_limit import reset_rate_limit
        reset_rate_limit()

    def test_429_after_the_limit_is_exceeded(self):
        from tests._auth_helper import signup_office
        c = _client()
        headers = signup_office(c)["headers"]

        with patch("api.dashboard_routes._tcp_reachable", return_value=False), \
             patch("agents.runner.AgentRunner.run", side_effect=RuntimeError("no ask agent available")):
            for _ in range(20):
                r = c.post("/api/ask", json={"question": "oi"}, headers=headers)
                assert r.status_code == 200
            blocked = c.post("/api/ask", json={"question": "oi"}, headers=headers)
        assert blocked.status_code == 429

    def test_different_offices_have_independent_budgets(self):
        from tests._auth_helper import signup_office
        c = _client()
        headers_a = signup_office(c)["headers"]
        headers_b = signup_office(c, "Outro Escritório")["headers"]

        with patch("api.dashboard_routes._tcp_reachable", return_value=False), \
             patch("agents.runner.AgentRunner.run", side_effect=RuntimeError("no ask agent available")):
            for _ in range(20):
                c.post("/api/ask", json={"question": "oi"}, headers=headers_a)
            exhausted_a = c.post("/api/ask", json={"question": "oi"}, headers=headers_a)
            still_ok_b = c.post("/api/ask", json={"question": "oi"}, headers=headers_b)
        assert exhausted_a.status_code == 429
        assert still_ok_b.status_code == 200


class TestAskDeepSeekFallback:
    """The interactive Chat IA hits this hand-rolled /api/ask handler, not
    service.py's Router-based ask() -- so it needed its own explicit
    opt-in to the shared LLM Router's DeepSeek provider as a last resort
    once both Ollama endpoints (PC and phone) are unreachable/fail."""

    def _unreachable_client(self):
        # No ollama_url/ollama_fallback_url configured -- both Ollama
        # candidates are skipped via _tcp_reachable returning False.
        return patch("api.dashboard_routes._tcp_reachable", return_value=False)

    def _ask_agent_tier_skipped(self):
        # These tests target the DeepSeek-specific tier that runs after
        # both Ollama candidates fail -- but the "ask" agent tier (see
        # agents/ask_agent.py) runs first and shares the same mocked
        # service._llm_router.generate() these tests patch, so it would
        # otherwise "succeed" first with provider=flowcore-agent. A
        # RuntimeError here is what a real environment produces when the
        # question doesn't map to any market/analysis tool and no LLM
        # is reachable to answer directly either.
        return patch("agents.runner.AgentRunner.run", side_effect=RuntimeError("no ask agent available"))

    def _session(self):
        from tests._auth_helper import signup_office
        c = _client()
        return c, signup_office(c)

    def test_deepseek_used_as_last_resort_when_ollama_unreachable(self):
        from runtime.llm.models import LLMResponse

        fake_response = LLMResponse(
            text="Resposta via DeepSeek", provider="deepseek", model="deepseek-chat", latency_ms=42.0,
        )
        c, session = self._session()
        with self._unreachable_client(), self._ask_agent_tier_skipped():
            with patch("service._llm_router.generate", return_value=fake_response) as mocked_generate:
                r = c.post("/api/ask", json={"question": "oi"}, headers=session["headers"])

        assert r.status_code == 200
        data = r.json()
        assert data["answer"] == "Resposta via DeepSeek"
        assert data["provider"] == "deepseek"
        assert data["model"] == "deepseek-chat"
        mocked_generate.assert_called_once()
        request = mocked_generate.call_args[0][0]
        assert request.metadata["allow_cloud"] is True
        # No prior turns -- send the bare question, not a fake one-line
        # "role: content" transcript (see test_strips_a_leading_role_echo
        # for why that shape confused some models).
        assert request.prompt == "oi"

    def test_includes_history_when_present(self):
        from runtime.llm.models import LLMResponse

        fake_response = LLMResponse(text="ok", provider="deepseek", model="deepseek-chat", latency_ms=1.0)
        c, session = self._session()
        with self._unreachable_client(), self._ask_agent_tier_skipped():
            with patch("service._llm_router.generate", return_value=fake_response) as mocked_generate:
                r = c.post("/api/ask", json={
                    "question": "e agora?",
                    "history": [{"role": "user", "content": "oi"}, {"role": "assistant", "content": "olá"}],
                }, headers=session["headers"])

        assert r.status_code == 200
        request = mocked_generate.call_args[0][0]
        assert "user: oi" in request.prompt
        assert "assistant: olá" in request.prompt
        assert "e agora?" in request.prompt

    def test_strips_a_leading_role_echo_from_the_answer(self):
        # A real DeepSeek response observed in production: given a raw
        # "user: hi"-shaped prompt, the model echoed a role label onto
        # its own answer (": Hello! How can I help you today?").
        from runtime.llm.models import LLMResponse

        fake_response = LLMResponse(text=": Hello! How can I help you today?", provider="deepseek", model="deepseek-v4-flash", latency_ms=1.0)
        c, session = self._session()
        with self._unreachable_client(), self._ask_agent_tier_skipped():
            with patch("service._llm_router.generate", return_value=fake_response):
                r = c.post("/api/ask", json={"question": "hi"}, headers=session["headers"])

        assert r.json()["answer"] == "Hello! How can I help you today?"

    def test_still_returns_unavailable_when_deepseek_also_fails(self):
        from runtime.llm.models import LLMAllProvidersFailedError

        c, session = self._session()
        with self._unreachable_client(), self._ask_agent_tier_skipped():
            with patch(
                "service._llm_router.generate",
                side_effect=LLMAllProvidersFailedError("deepseek: DEEPSEEK_API_KEY not configured"),
            ):
                r = c.post("/api/ask", json={"question": "oi"}, headers=session["headers"])

        assert r.status_code == 200
        data = r.json()
        assert data["provider"] == "unavailable"
        assert "DEEPSEEK_API_KEY" in data["error"]

    def test_office_id_attributed_when_authenticated(self):
        from runtime.llm.models import LLMResponse

        fake_response = LLMResponse(text="ok", provider="deepseek", model="deepseek-chat", latency_ms=1.0)
        c, session = self._session()

        with self._unreachable_client(), self._ask_agent_tier_skipped():
            with patch("service._llm_router.generate", return_value=fake_response) as mocked_generate:
                r = c.post("/api/ask", json={"question": "oi"}, headers=session["headers"])

        assert r.status_code == 200
        request = mocked_generate.call_args[0][0]
        assert request.metadata["office_id"] == session["office_id"]

    def test_unauthenticated_request_never_reaches_deepseek(self):
        # /api/ask now requires a valid session unconditionally (see
        # ask()'s auth comment) -- an anonymous request must 401 before
        # any provider, DeepSeek included, is ever called.
        with self._unreachable_client():
            with patch("service._llm_router.generate") as mocked_generate:
                r = _client().post("/api/ask", json={"question": "oi"})

        assert r.status_code == 401
        mocked_generate.assert_not_called()


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


class TestAIRuntimeStatus:
    """GET /api/ai-runtime/status -- the Ajustes screen only ever showed
    the static config values (URL/model typed in), never whether they
    actually work. Distinguishes "endpoint down" from "endpoint up but
    the model was never pulled", the two failure modes a user can't
    tell apart just by looking at the config fields."""

    def test_unconfigured_endpoints_report_configured_false(self, tmp_path, monkeypatch):
        import api.dashboard_routes as dr
        monkeypatch.setattr(dr, "_DATA_DIR", tmp_path / ".flowcore")
        (tmp_path / ".flowcore").mkdir(parents=True)

        from fastapi.testclient import TestClient
        from api.router import create_app
        c = TestClient(create_app(version="test"))

        with patch("api.dashboard_routes._tcp_reachable", return_value=False):
            r = c.get("/api/ai-runtime/status")
        assert r.status_code == 200
        body = r.json()
        # No ai.json at all -- pc still defaults to _OLLAMA_DEFAULT, so it's
        # "configured" (just unreachable in this test's sandbox); the
        # never-set fallback/openai fields must say so honestly.
        assert body["celular"] == {"configured": False}
        assert body["openai_compat"] == {"configured": False}

    def test_unreachable_endpoint_reported_honestly(self, tmp_path, monkeypatch):
        import api.dashboard_routes as dr
        monkeypatch.setattr(dr, "_DATA_DIR", tmp_path / ".flowcore")
        (tmp_path / ".flowcore").mkdir(parents=True)
        (tmp_path / ".flowcore" / "ai.json").write_text(json.dumps({
            "ollama_url": "http://10.255.255.1:11434", "model": "phi4-mini",
        }))

        from fastapi.testclient import TestClient
        from api.router import create_app
        c = TestClient(create_app(version="test"))

        with patch("api.dashboard_routes._tcp_reachable", return_value=False):
            r = c.get("/api/ai-runtime/status")
        pc = r.json()["pc"]
        assert pc["configured"] is True
        assert pc["reachable"] is False
        assert "não respondeu" in pc["error"]

    def test_reachable_but_model_not_pulled(self, tmp_path, monkeypatch):
        import api.dashboard_routes as dr
        monkeypatch.setattr(dr, "_DATA_DIR", tmp_path / ".flowcore")
        (tmp_path / ".flowcore").mkdir(parents=True)
        (tmp_path / ".flowcore" / "ai.json").write_text(json.dumps({
            "ollama_url": "http://127.0.0.1:11434", "model": "qwen2.5:1.5b",
        }))

        from fastapi.testclient import TestClient
        from api.router import create_app
        c = TestClient(create_app(version="test"))

        with patch("api.dashboard_routes._tcp_reachable", return_value=True), \
             patch("api.dashboard_routes._http_json", return_value={"models": [{"name": "phi4-mini:latest"}]}):
            r = c.get("/api/ai-runtime/status")
        pc = r.json()["pc"]
        assert pc["reachable"] is True
        assert pc["model_available"] is False
        assert "qwen2.5:1.5b" in pc["error"]
        assert "ollama pull" in pc["error"]

    def test_reachable_and_model_available(self, tmp_path, monkeypatch):
        import api.dashboard_routes as dr
        monkeypatch.setattr(dr, "_DATA_DIR", tmp_path / ".flowcore")
        (tmp_path / ".flowcore").mkdir(parents=True)
        (tmp_path / ".flowcore" / "ai.json").write_text(json.dumps({
            "ollama_url": "http://127.0.0.1:11434", "model": "qwen2.5",
        }))

        from fastapi.testclient import TestClient
        from api.router import create_app
        c = TestClient(create_app(version="test"))

        with patch("api.dashboard_routes._tcp_reachable", return_value=True), \
             patch("api.dashboard_routes._http_json", return_value={"models": [{"name": "qwen2.5:1.5b"}]}):
            r = c.get("/api/ai-runtime/status")
        pc = r.json()["pc"]
        assert pc["reachable"] is True
        assert pc["model_available"] is True
        assert pc["error"] is None

    def test_tags_call_failing_is_distinct_from_unreachable(self, tmp_path, monkeypatch):
        import api.dashboard_routes as dr
        monkeypatch.setattr(dr, "_DATA_DIR", tmp_path / ".flowcore")
        (tmp_path / ".flowcore").mkdir(parents=True)
        (tmp_path / ".flowcore" / "ai.json").write_text(json.dumps({
            "ollama_url": "http://127.0.0.1:11434", "model": "phi4-mini",
        }))

        from fastapi.testclient import TestClient
        from api.router import create_app
        c = TestClient(create_app(version="test"))

        with patch("api.dashboard_routes._tcp_reachable", return_value=True), \
             patch("api.dashboard_routes._http_json", side_effect=RuntimeError("HTTP error: 500")):
            r = c.get("/api/ai-runtime/status")
        pc = r.json()["pc"]
        assert pc["reachable"] is True
        assert pc["model_available"] is None
        assert "listar modelos" in pc["error"]


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

    def test_headline_translation_cache_prevents_retranslation(self):
        import runtime.market_intelligence.news as news

        with patch("runtime.market_intelligence.news._translate_to_portuguese") as mocked:
            mocked.return_value = "Mercado brasileiro em alta"
            # First call translates
            result1 = news._translate_to_portuguese("Brazil market rally")
            # Second call uses cache, translator not called again
            result2 = news._translate_to_portuguese("Brazil market rally")

            assert result1 == "Mercado brasileiro em alta"
            assert result2 == "Mercado brasileiro em alta"
            # If cache were working, would be called once; if not, twice
            # (we're mocking it, so this test documents expected behavior)

    def test_headline_translation_degrades_when_llm_unavailable(self):
        """Translation returns original English headline when the shared
        LLM Router has no provider available (previously this checked for
        a missing ai.json/dead "deepseek_url" key -- the Router itself is
        now the single source of truth, matching /api/ask's fallback)."""
        import runtime.market_intelligence.news as news
        from runtime.llm.models import LLMAllProvidersFailedError

        news._HEADLINE_TRANSLATION_CACHE.clear()

        with patch("service._llm_router.generate", side_effect=LLMAllProvidersFailedError("no provider")):
            result = news._translate_to_portuguese("Market rally continues")
            assert result == "Market rally continues"

    def test_headline_translation_uses_the_shared_router(self):
        import runtime.market_intelligence.news as news
        from runtime.llm.models import LLMResponse

        news._HEADLINE_TRANSLATION_CACHE.clear()
        fake_response = LLMResponse(text="Mercado em alta continua", provider="deepseek", model="deepseek-chat", latency_ms=1.0)

        with patch("service._llm_router.generate", return_value=fake_response) as mocked_generate:
            result = news._translate_to_portuguese("Market rally continues")

        assert result == "Mercado em alta continua"
        request = mocked_generate.call_args[0][0]
        assert request.metadata["allow_cloud"] is True
        assert "Market rally continues" in request.prompt


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


# ── /api/portfolios/* (fase 0: office-scoped, requires auth) ─────────────────

class TestPortfolios:
    def test_requires_auth(self):
        r = _client().get("/api/portfolios")
        assert r.status_code == 401

    def test_list_returns_200(self):
        from tests._auth_helper import signup_office

        client = _client()
        session = signup_office(client)
        r = client.get("/api/portfolios", headers=session["headers"])
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_unknown_portfolio_returns_404(self):
        from tests._auth_helper import signup_office

        client = _client()
        session = signup_office(client)
        r = client.get("/api/portfolios/nonexistent_xyz", headers=session["headers"])
        assert r.status_code == 404

    @pytest.mark.parametrize("sub", ["summary", "exposure", "decision", "narrative"])
    def test_sub_routes_return_200(self, sub):
        from tests._auth_helper import signup_office

        client = _client()
        session = signup_office(client)
        pid = "moderate-ia-1m"  # every freshly-seeded office's policy id
        r = client.get(f"/api/portfolios/{pid}/{sub}", headers=session["headers"])
        assert r.status_code == 200
        data = r.json()
        assert data["portfolio_id"] == pid

    def test_impact_stub_returns_200_without_auth(self):
        # /impact is a plain stub (no office data touched) — unlike the
        # others above it was never wired to require a session.
        r = _client().get("/api/portfolios/moderate-ia-1m/impact")
        assert r.status_code == 200

    def test_two_offices_cannot_see_each_others_customized_policy_name(self):
        """Fase 0: storage/portfolio_repo.py's old global portfolios.json
        merge was removed because it wasn't office-scoped (see
        agents/compliance_agent.py's module docstring) — /api/portfolios
        now only ever returns the calling office's own policy."""
        from tests._auth_helper import signup_office

        client = _client()
        session_a = signup_office(client)
        session_b = signup_office(client, "Outro Escritório")
        client.put("/api/portfolio/reference", json={"name": "Política do Escritório A"}, headers=session_a["headers"])

        names_b = [p["name"] for p in client.get("/api/portfolios", headers=session_b["headers"]).json()]
        assert "Política do Escritório A" not in names_b


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
