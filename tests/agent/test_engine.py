"""Tests for runtime.agent.engine.AgentEngine -- tool selection, real
execution, and grounded response synthesis.

Core tier — a real LLMRouter wired with a fake in-test LLMProvider (no
network, no runtime/ollama.py involved), matching
tests/narrative/test_engine.py's established convention. Tools are
in-test stubs (mocking the LLM is expected per this project's test
policy; a separate E2E path exercises the real service.py tools against
a real provider when credentials are available).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _ScriptedProvider:
    """Returns each of `texts` in order across successive generate()
    calls (repeating the last one if called more times than scripted) --
    needed because a tool call drives two sequential Router calls
    (selection, then result-grounding)."""

    name = "fake"

    def __init__(self, texts, fail_with=None):
        self._texts = list(texts)
        self._fail_with = fail_with
        self._last_text = ""
        self.calls = []

    def is_available(self):
        return True

    def generate(self, request):
        from runtime.llm import LLMResponse

        self.calls.append(request)
        if self._fail_with:
            raise self._fail_with
        if self._texts:
            self._last_text = self._texts.pop(0)
        return LLMResponse(text=self._last_text, provider=self.name, model="fake-model", latency_ms=1.0)


def _router_with(provider):
    from runtime.llm import LocalFirstPolicy, ProviderRegistry
    from runtime.llm.router import LLMRouter

    registry = ProviderRegistry()
    registry.register(provider)

    class _AlwaysAllowPolicy(LocalFirstPolicy):
        def choose(self, request, available):
            return list(available)

    return LLMRouter(registry, _AlwaysAllowPolicy())


def _tool(name, handler, description="desc", parameters=None):
    from runtime.agent.models import ToolSpec

    return ToolSpec(name=name, description=description, handler=handler, parameters=parameters or {})


class TestToolSelection:
    def test_selects_doctor_and_executes_it_for_real(self):
        """1. selecao de doctor / 2. execucao real (mockada) da funcao Doctor."""
        from runtime.agent.engine import AgentEngine

        calls = []

        async def fake_doctor():
            calls.append("ran")
            return {"healthy": True, "passed": 30, "failed": 0}

        provider = _ScriptedProvider(
            [
                '{"tool": "doctor", "arguments": {}, "answer": ""}',
                "Diagnostico concluido: 30 checks OK, sistema saudavel.",
            ]
        )
        engine = AgentEngine(_router_with(provider), [_tool("doctor", fake_doctor)])

        result = asyncio.run(engine.handle("Faca o diagnostico do meu sistema."))

        assert calls == ["ran"]  # the tool was actually invoked, not just claimed
        assert result.tool_used == "doctor"
        assert result.tool_result == {"healthy": True, "passed": 30, "failed": 0}
        assert "saudavel" in result.answer

    def test_selects_memory_save_and_persists(self):
        """3. selecao de memory_save / 4. persistencia da memoria."""
        from runtime.agent.engine import AgentEngine

        store = []

        async def fake_memory_save(text):
            store.append(text)
            return {"text": text, "saved": True}

        provider = _ScriptedProvider(
            [
                '{"tool": "memory_save", "arguments": {"text": "prioridade: internacionalizacao"}}',
                "Guardado: sua prioridade e internacionalizacao.",
            ]
        )
        engine = AgentEngine(_router_with(provider), [_tool("memory_save", fake_memory_save)])

        result = asyncio.run(engine.handle("Guarde que minha prioridade e internacionalizacao."))

        assert store == ["prioridade: internacionalizacao"]
        assert result.tool_used == "memory_save"

    def test_selects_note_save_and_persists(self):
        """5. selecao de note_save / 6. persistencia da nota."""
        from runtime.agent.engine import AgentEngine

        store = []

        async def fake_note_save(text, kind="note"):
            store.append((text, kind))
            return {"id": 1, "kind": kind, "text": text}

        provider = _ScriptedProvider(
            [
                '{"tool": "note_save", "arguments": {"text": "revisar duration amanha"}}',
                "Nota criada: revisar duration amanha.",
            ]
        )
        engine = AgentEngine(_router_with(provider), [_tool("note_save", fake_note_save)])

        result = asyncio.run(engine.handle("Anote que preciso revisar duration amanha."))

        assert store == [("revisar duration amanha", "note")]
        assert result.tool_used == "note_save"

    def test_selects_portfolio_summary(self):
        """7. portfolio."""
        from runtime.agent.engine import AgentEngine

        async def fake_portfolio_summary(portfolio_id):
            return {"portfolio_id": portfolio_id, "total_value": 1000.0}

        provider = _ScriptedProvider(
            [
                '{"tool": "portfolio_summary", "arguments": {"portfolio_id": 1}}',
                "Sua carteira 1 vale 1000.",
            ]
        )
        engine = AgentEngine(_router_with(provider), [_tool("portfolio_summary", fake_portfolio_summary)])

        result = asyncio.run(engine.handle("Mostre o resumo da minha carteira."))

        assert result.tool_used == "portfolio_summary"
        assert result.tool_result == {"portfolio_id": 1, "total_value": 1000.0}


class TestGracefulDegradation:
    def test_nonexistent_tool_falls_back_without_crashing(self):
        """8. ferramenta inexistente."""
        from runtime.agent.engine import AgentEngine

        provider = _ScriptedProvider(['{"tool": "delete_everything", "arguments": {}, "answer": ""}'])
        engine = AgentEngine(_router_with(provider), [])

        result = asyncio.run(engine.handle("faz algo"))

        assert result.tool_used is None

    def test_invalid_json_falls_back_to_raw_text(self):
        """9. JSON invalido."""
        from runtime.agent.engine import AgentEngine

        provider = _ScriptedProvider(["isso nao e json"])
        engine = AgentEngine(_router_with(provider), [])

        result = asyncio.run(engine.handle("oi"))

        assert result.tool_used is None
        assert result.answer == "isso nao e json"

    def test_llm_unavailable_propagates_llm_error(self):
        """10. LLM indisponivel."""
        from runtime.agent.engine import AgentEngine
        from runtime.llm import LLMProviderUnavailableError

        provider = _ScriptedProvider([], fail_with=LLMProviderUnavailableError("ollama down"))
        engine = AgentEngine(_router_with(provider), [])

        with pytest.raises(LLMProviderUnavailableError):
            asyncio.run(engine.handle("oi"))

    def test_tool_execution_failure_is_reported_not_raised(self):
        """11. tool execution failure."""
        from runtime.agent.engine import AgentEngine

        async def broken_doctor():
            raise RuntimeError("disco cheio")

        provider = _ScriptedProvider(['{"tool": "doctor", "arguments": {}}'])
        engine = AgentEngine(_router_with(provider), [_tool("doctor", broken_doctor)])

        result = asyncio.run(engine.handle("diagnostico"))

        assert result.tool_used == "doctor"
        assert "disco cheio" in result.answer
        assert result.tool_result is None

    def test_value_error_from_tool_is_surfaced_as_clarification(self):
        """Ambiguous/missing argument (e.g. which portfolio?) — a ValueError
        from the tool becomes the answer verbatim, not a generic failure."""
        from runtime.agent.engine import AgentEngine

        async def ambiguous_portfolio():
            raise ValueError("Existe mais de uma carteira -- diga qual.")

        provider = _ScriptedProvider(['{"tool": "portfolio_summary", "arguments": {}}'])
        engine = AgentEngine(_router_with(provider), [_tool("portfolio_summary", ambiguous_portfolio)])

        result = asyncio.run(engine.handle("resumo da carteira"))

        assert result.answer == "Existe mais de uma carteira -- diga qual."

    def test_missing_required_argument_asks_for_clarification_not_crash(self):
        async def note_save(text, kind="note"):
            return {"text": text, "kind": kind}

        from runtime.agent.engine import AgentEngine

        provider = _ScriptedProvider(['{"tool": "note_save", "arguments": {}}'])
        engine = AgentEngine(_router_with(provider), [_tool("note_save", note_save)])

        result = asyncio.run(engine.handle("anota ai"))

        assert result.tool_used == "note_save"
        assert "note_save" in result.answer

    def test_response_without_tool_uses_direct_answer(self):
        """12. resposta sem tool."""
        from runtime.agent.engine import AgentEngine

        provider = _ScriptedProvider(['{"tool": null, "arguments": {}, "answer": "Ola! Como posso ajudar?"}'])
        engine = AgentEngine(_router_with(provider), [])

        result = asyncio.run(engine.handle("oi"))

        assert result.tool_used is None
        assert result.answer == "Ola! Como posso ajudar?"


class TestFinalAnswerLLMFailure:
    def test_second_call_failure_degrades_to_deterministic_rendering(self):
        """The tool already ran and produced a real result -- if only the
        grounding call fails, the request must not fail either."""
        from runtime.agent.engine import AgentEngine
        from runtime.llm import LLMProviderUnavailableError

        class _FirstOkThenFails:
            name = "fake"

            def __init__(self):
                self.call_count = 0

            def is_available(self):
                return True

            def generate(self, request):
                from runtime.llm import LLMResponse

                self.call_count += 1
                if self.call_count == 1:
                    return LLMResponse(
                        text='{"tool": "doctor", "arguments": {}}', provider=self.name, model="m", latency_ms=1.0
                    )
                raise LLMProviderUnavailableError("down mid-flow")

        async def fake_doctor():
            return {"healthy": True}

        engine = AgentEngine(_router_with(_FirstOkThenFails()), [_tool("doctor", fake_doctor)])
        result = asyncio.run(engine.handle("diagnostico"))

        assert result.tool_used == "doctor"
        assert result.tool_result == {"healthy": True}
        assert "doctor" in result.answer  # deterministic fallback rendering, not a crash
