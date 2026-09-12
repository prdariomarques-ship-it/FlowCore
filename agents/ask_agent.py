"""AskAgent -- wraps runtime/agent/engine.py's AgentEngine (free-text
tool-calling) as a regular BaseAgent, so AgentRunner becomes a single
entry point for both scheduled/autonomous agents (MarketAgent,
ComplianceAgent, ...) and interactive tool-calling like this one.

Before this existed, api/dashboard_routes.py's /api/ask had an
`if "ask" in agents:` branch that could never fire -- no agent named
"ask" was ever auto-registered, so the multi-office Chat IA never got
any of AgentEngine's real tools (runtime/ai_runtime.py's own docstring
already documented "Chat com contexto: reutiliza service.agent_ask()"
as the intended design, but nothing wired it up) and fell straight to a
raw, tool-less Ollama/OpenAI/DeepSeek chat instead.

Deliberately NOT the same AgentEngine instance service.agent_ask() uses
for the CLI/MCP (service._agent_engine, exposing all 18 tools).
memory_save/memory_recall/note_save/portfolio_summary/portfolio_impact/
portfolio_exposure/portfolio_recommendations there are FlowCore's
original single-user personal-assistant tools -- no office_id anywhere
(see service.py's _memory_save_tool etc.). Wiring those into this
multi-office agent would let one office read or write another's
"memory"/notes/portfolio through chat -- a real cross-tenant leak.
Only the market_* tools and regime_signals are global, read-only market
data with no tenant concept at all, so those are the only ones exposed
here.
"""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent

_ALLOWED_TOOL_PREFIXES = ("market_",)
_ALLOWED_TOOL_NAMES = frozenset({"regime_signals"})


def _is_tenant_safe(tool_name: str) -> bool:
    return tool_name in _ALLOWED_TOOL_NAMES or tool_name.startswith(_ALLOWED_TOOL_PREFIXES)


def _build_engine():
    # Lazy import -- service.py is FlowCore's composition root (LLM
    # Router + full tool catalog) and is never imported at module level
    # from agents/ or api/, matching the existing convention (see
    # api/dashboard_routes.py's DeepSeek fallback in /api/ask).
    from runtime.agent.engine import AgentEngine
    from service import _agent_tools, _llm_router

    safe_tools = [t for t in _agent_tools if _is_tenant_safe(t.name)]
    return AgentEngine(_llm_router, safe_tools)


class AskAgent(BaseAgent):
    name = "ask"
    description = (
        "Responde perguntas livres com acesso as tools de mercado/analise "
        "do FlowCore (correlacao, risco, rebalance, yield curve, FX, "
        "noticias, regime macro) -- sem acesso a memoria, notas ou "
        "carteira pessoal, que nao sao escopadas por escritorio."
    )
    version = "0.1.0"

    async def run(self, context: dict | None = None) -> dict[str, Any]:
        question = (context or {}).get("question", "").strip()
        if not question:
            return {"status": "error", "data": {"reason": "empty question"}}

        engine = _build_engine()
        try:
            result = await engine.handle(question)
        except Exception as exc:  # noqa: BLE001 -- degrade, caller falls back to raw chat
            return {"status": "error", "data": {"reason": str(exc)}}
        return {"status": "ok", "data": result.to_dict()}
