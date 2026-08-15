"""Tests for the AI Runtime layer (model selector, memory control, health).

All Ollama HTTP calls (``/api/tags``, ``/api/ps``, ``/api/generate``) are
mocked -- the module only composes stdlib urllib + runtime.ollama helpers,
whose own behavior is covered by tests/llm/test_ollama_provider.py.
"""
from __future__ import annotations

import json
from unittest import mock

import pytest

TAGS_RESPONSE = {
    "models": [
        {
            "name": "qwen3:4b",
            "size": 2497293931,
            "details": {"parameter_size": "4.0B", "families": ["qwen3"]},
        },
        {
            "name": "deepseek-r1:8b",
            "size": 5200000000,
            "details": {"parameter_size": "8.0B", "families": ["deepseek-r1"]},
        },
        {"name": "glm-5.2:cloud", "size": 0, "remote_host": "ollama.com", "details": {}},
    ]
}

PS_RESPONSE = {
    "models": [
        {"name": "qwen3:4b", "size_vram": 3400000000, "details": {"parameter_size": "4.0B"}},
    ]
}


def _ollama_mocks(tags: dict = TAGS_RESPONSE, ps: dict = PS_RESPONSE, generate_ok: bool = True):
    urlopen_responses = {"tags": tags, "ps": ps, "generate": '{"response":"","done":true}'}

    def urlopen(req, timeout=5):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/api/tags" in url:
            body = json.dumps(urlopen_responses["tags"])
        elif "/api/ps" in url:
            body = json.dumps(urlopen_responses["ps"])
        else:
            body = urlopen_responses["generate"] if generate_ok else ""
        resp = mock.MagicMock()
        resp.read.return_value = body.encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = lambda *a: False
        return resp

    return mock.patch("urllib.request.urlopen", side_effect=urlopen)


@pytest.fixture(autouse=True)
def _patch_discovery():
    with mock.patch("runtime.ai_runtime._ollama_base_url", return_value="http://127.0.0.1:11434"), \
         mock.patch("runtime.ai_runtime.ensure_model_loaded"), \
         mock.patch("runtime.ai_runtime.discover_default_model", return_value="qwen3:4b"):
        yield


class TestModelList:
    def test_lists_models_with_sizes_and_loaded_flag(self):
        from runtime.ai_runtime import model_list

        with _ollama_mocks():
            data = model_list()
        names = {m["name"] for m in data["models"]}
        assert names == {"qwen3:4b", "deepseek-r1:8b", "glm-5.2:cloud"}
        sizes = {m["name"]: m["size_gb"] for m in data["models"]}
        assert sizes["qwen3:4b"] == "2.33"
        assert data["ollama_available"] is True
        assert "qwen3:4b" in data["loaded"]
        assert "deepseek-r1:8b" not in data["loaded"]
        assert data["active_model"] is not None

    def test_degrades_when_ollama_unreachable(self):
        from runtime.ai_runtime import model_list
        from runtime.ollama import OllamaUnreachableError

        with mock.patch("runtime.ai_runtime.list_loaded_models", side_effect=OllamaUnreachableError("x")):
            data = model_list()
        assert data["ollama_available"] is False
        assert data["models"] == []


class TestMemoryStatus:
    def test_reports_loaded_models_and_ram(self):
        from runtime.ai_runtime import memory_status

        with _ollama_mocks():
            data = memory_status()
        assert data["ollama_available"] is True
        assert data["total_ram_used_gb"] == "3.17"


class TestLoadUnload:
    def test_load_model_success(self):
        from runtime.ai_runtime import load_model

        with _ollama_mocks():
            result = load_model("qwen3:4b", timeout=60)
        assert result["ok"] is True
        assert result["model"] == "qwen3:4b"
        assert result["loaded"] is True

    def test_load_unknown_model(self):
        from runtime.ai_runtime import load_model

        with _ollama_mocks():
            result = load_model("nao-existe:latest", timeout=60)
        assert result["ok"] is False
        assert result["error"] == "model_not_installed"

    def test_unload_clears_model(self):
        from runtime.ai_runtime import unload_model

        with _ollama_mocks(ps={"models": []}):  # /api/ps vazio após descarregar
            result = unload_model("qwen3:4b")
        assert result["ok"] is True
        assert result["loaded"] is False


class TestAiRuntimeHealth:
    def test_health_combines_availability_and_model_state(self):
        from runtime.ai_runtime import ai_runtime_health

        with _ollama_mocks():
            data = ai_runtime_health()
        assert data["ai_runtime"] is True
        assert data["ollama_available"] is True
        assert data["default_model"] is not None
        assert data["local_first"] is True


class TestAiRuntimePolicy:
    def test_writes_selected_model_and_allow_cloud_into_metadata(self):
        from service import _AiRuntimePolicy

        inner = mock.MagicMock()
        inner.choose.return_value = ["ollama"]
        request = mock.MagicMock()
        request.metadata = {"purpose": "agent"}

        policy = _AiRuntimePolicy(inner, selected_model="gemma3:4b", allow_cloud=True)
        policy.choose(request, ["ollama"])

        inner.choose.assert_called_once()
        meta = request.metadata
        assert meta["selected_model"] == "gemma3:4b"
        assert meta["allow_cloud"] is True
        assert meta["purpose"] == "agent"

    def test_no_overrides_when_none(self):
        from service import _AiRuntimePolicy

        inner = mock.MagicMock()
        inner.choose.return_value = ["ollama"]
        request = mock.MagicMock()
        request.metadata = {"purpose": "agent"}

        _AiRuntimePolicy(inner).choose(request, ["ollama"])
        assert request.metadata == {"purpose": "agent"}
