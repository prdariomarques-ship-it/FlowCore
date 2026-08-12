"""E2E test for the Agent Engine against a real LLM provider, exercised
through service.py's real tool wiring (real DoctorService, real
MemoryRepository) -- not the in-test stubs test_engine.py uses.

Skipped when no LLM provider is reachable (typical in CI without Ollama
or an OPENROUTER_API_KEY). Run locally / on the target device where a
real provider is configured to get real coverage -- this is the "at
least one E2E test using a real provider when credentials are available"
test this suite is required to have.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _llm_reachable() -> bool:
    from runtime.ollama import OllamaDiscoveryError, discover_ollama_endpoint

    try:
        discover_ollama_endpoint()
        return True
    except OllamaDiscoveryError:
        import os

        return bool(os.getenv("OPENROUTER_API_KEY"))


@pytest.mark.skipif(not _llm_reachable(), reason="no reachable LLM provider (Ollama/OpenRouter) for a real E2E call")
def test_doctor_end_to_end_with_real_llm_and_real_tool():
    import service

    result = asyncio.run(service.agent_ask("Faca o diagnostico do meu sistema.", timeout=180))

    assert result["tool_used"] == "doctor"
    assert result["tool_result"] is not None
    assert "healthy" in result["tool_result"]
    assert result["answer"]


@pytest.mark.skipif(not _llm_reachable(), reason="no reachable LLM provider (Ollama/OpenRouter) for a real E2E call")
def test_memory_save_end_to_end_with_real_llm_and_real_persistence():
    import uuid

    import service

    marker = f"e2e-agent-test-{uuid.uuid4().hex[:8]}"
    result = asyncio.run(service.agent_ask(f"Guarde na memoria o seguinte texto: {marker}", timeout=180))

    assert result["tool_used"] == "memory_save"
    matches = service._mem_repo.search(marker)
    assert any(marker in m["text"] for m in matches)
