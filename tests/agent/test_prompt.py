"""Tests for runtime.agent.prompt -- tool-catalog prompt construction and
defensive parsing of the model's JSON decision.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _tool(name="doctor", description="Executa o diagnostico.", parameters=None):
    from runtime.agent.models import ToolSpec

    async def _handler(**_kwargs):
        return {}

    return ToolSpec(name=name, description=description, handler=_handler, parameters=parameters or {})


class TestBuildPrompt:
    def test_includes_tool_names_and_descriptions(self):
        from runtime.agent.prompt import build_prompt

        prompt = build_prompt("oi", [_tool(name="doctor", description="Diagnostico real.")])
        assert "doctor" in prompt
        assert "Diagnostico real." in prompt

    def test_includes_question_and_context(self):
        from runtime.agent.prompt import build_prompt

        prompt = build_prompt("Qual minha prioridade?", [_tool()], context="Contexto: prioridade e i18n.")
        assert "Qual minha prioridade?" in prompt
        assert "prioridade e i18n" in prompt

    def test_no_context_omits_context_section(self):
        from runtime.agent.prompt import build_prompt

        prompt = build_prompt("oi", [_tool()], context="")
        assert "Contexto:" not in prompt


class TestParseToolCall:
    def test_parses_bare_json(self):
        from runtime.agent.prompt import parse_tool_call

        decision = parse_tool_call('{"tool": "doctor", "arguments": {}, "answer": ""}')
        assert decision == {"tool": "doctor", "arguments": {}, "answer": ""}

    def test_parses_json_inside_markdown_fence(self):
        from runtime.agent.prompt import parse_tool_call

        text = '```json\n{"tool": "note_save", "arguments": {"text": "x"}}\n```'
        decision = parse_tool_call(text)
        assert decision["tool"] == "note_save"
        assert decision["arguments"] == {"text": "x"}

    def test_tolerates_stray_text_around_the_object(self):
        from runtime.agent.prompt import parse_tool_call

        text = 'Claro, aqui esta: {"tool": null, "answer": "ok"} espero que ajude'
        decision = parse_tool_call(text)
        assert decision["tool"] is None
        assert decision["answer"] == "ok"

    def test_invalid_json_returns_none(self):
        from runtime.agent.prompt import parse_tool_call

        assert parse_tool_call("isso nao e json de jeito nenhum") is None

    def test_json_without_tool_key_returns_none(self):
        from runtime.agent.prompt import parse_tool_call

        assert parse_tool_call('{"foo": "bar"}') is None

    def test_empty_string_returns_none(self):
        from runtime.agent.prompt import parse_tool_call

        assert parse_tool_call("") is None
