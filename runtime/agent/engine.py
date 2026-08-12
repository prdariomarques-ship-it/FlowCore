"""AgentEngine -- the tool-calling layer between free-text user intent and
FlowCore's real, deterministic capabilities (Doctor, Memory, Notes,
Portfolio, ...). Mirrors runtime/narrative/engine.py's shape: a thin
class holding an injected LLMRouter, composed once in service.py exactly
like every other engine in this codebase (ImpactEngine(regime_engine),
NarrativeEngine(llm_router), ...).

Two-call design, matching "LLMs are language layers. Decision engines
belong to FlowCore" (FLOWCORE_CONSTITUTION.md, AI Philosophy):

  1. Selection call -- given the question, RAG context, and the tool
     catalog, the LLM either (a) picks a registered tool + arguments, or
     (b) answers directly (tool=null) when none applies. The LLM never
     executes anything itself -- it only ever names a tool already
     registered by service.py.
  2. If a tool was picked: FlowCore's own code validates it exists and
     executes the handler for real. A second, grounding-only call then
     turns that *real* result into natural language -- the model is
     shown nothing but the tool's actual output, so it cannot invent
     data the tool didn't return.

Tool execution failures never reach the LLM as something to explain
away -- ValueError (a tool asking for clarification -- e.g. "which
portfolio?") and any other exception (a genuine failure) both produce a
deterministic message directly, without a second LLM call, so a broken
or ambiguous tool call can never be narrated into looking like it
succeeded.
"""

from __future__ import annotations

import asyncio

from runtime.agent.models import AgentResult, ToolSpec
from runtime.agent.prompt import build_prompt, build_result_prompt, parse_tool_call
from runtime.llm import LLMError, LLMRequest, LLMRouter

__all__ = ["AgentEngine"]


class AgentEngine:
    def __init__(self, router: LLMRouter, tools: list[ToolSpec]) -> None:
        self._router = router
        self._tools = {t.name: t for t in tools}

    async def handle(self, question: str, context: str = "", timeout: float | None = None) -> AgentResult:
        """Raises LLMError (from the selection call) exactly like
        service.ask() already does -- callers (CLI/FastAPI/MCP) catch it
        the same way. Once a tool has actually run, failures are always
        absorbed into the returned AgentResult instead, never raised --
        a real result already exists by then and must be reported."""
        selection_prompt = build_prompt(question, list(self._tools.values()), context)
        request = LLMRequest(prompt=selection_prompt, timeout=timeout, metadata={"purpose": "agent"})
        response = await asyncio.to_thread(self._router.generate, request)

        decision = parse_tool_call(response.text)
        tool_name = decision.get("tool") if decision else None

        if not tool_name or tool_name not in self._tools:
            answer = (decision.get("answer") if decision else None) or response.text.strip()
            return AgentResult(answer=answer, model=response.model, tool_used=None)

        tool = self._tools[tool_name]
        arguments = decision.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}

        try:
            result = await tool.handler(**arguments)
        except TypeError as e:
            return AgentResult(
                answer=f"Nao consegui usar '{tool_name}' com os argumentos fornecidos: {e}",
                model=response.model,
                tool_used=tool_name,
            )
        except ValueError as e:
            # A tool deliberately asking for clarification (e.g. "which
            # portfolio?") -- its message is already the user-facing text.
            return AgentResult(answer=str(e), model=response.model, tool_used=tool_name)
        except Exception as e:
            return AgentResult(
                answer=f"A ferramenta '{tool_name}' falhou: {e}", model=response.model, tool_used=tool_name
            )

        final_prompt = build_result_prompt(question, tool_name, result)
        final_request = LLMRequest(prompt=final_prompt, timeout=timeout, metadata={"purpose": "agent_answer"})
        try:
            final_response = await asyncio.to_thread(self._router.generate, final_request)
            answer, model = final_response.text.strip(), final_response.model
        except LLMError:
            # The tool already ran and produced a real result -- degrade to
            # a deterministic rendering instead of failing the whole request.
            answer, model = f"'{tool_name}' executado. Resultado: {result}", response.model

        return AgentResult(answer=answer, model=model, tool_used=tool_name, tool_result=result)
