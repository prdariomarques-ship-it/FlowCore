"""Prompt construction and response parsing for the Agent Engine.

Two prompts, matching engine.py's two-call design:

- build_prompt(): selection call. Shows the model the tool catalog plus
  the same RAG context service.ask() already builds, and asks for a
  single JSON decision -- either a tool + arguments, or a direct answer
  grounded in the context (tool=null). No native function-calling API is
  assumed (Ollama/OpenRouter models vary), so the contract is plain
  prompt-engineered JSON, parsed defensively by parse_tool_call().

- build_result_prompt(): grounding call, used only after a tool actually
  ran. The model is shown nothing but the real tool result -- it cannot
  invent data the tool didn't return.
"""

from __future__ import annotations

import json
import re

__all__ = ["build_prompt", "build_result_prompt", "parse_tool_call"]

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)

_RESPONSE_SHAPE = (
    '{"tool": "<nome da ferramenta ou null>", "arguments": {...}, '
    '"answer": "<resposta direta, somente se tool for null>"}'
)


def _catalog(tools) -> str:
    lines = []
    for t in tools:
        params = ", ".join(f"{k} ({v})" for k, v in t.parameters.items()) or "nenhum"
        lines.append(f"- {t.name}: {t.description} Parametros: {params}.")
    return "\n".join(lines)


def build_prompt(question: str, tools, context: str = "") -> str:
    lines = [
        "Voce e o Agent do FlowCore. Estas sao as UNICAS ferramentas que voce pode escolher:",
        "",
        _catalog(tools),
        "",
        "Responda com APENAS um objeto JSON, sem markdown e sem texto fora do JSON, neste formato:",
        _RESPONSE_SHAPE,
        "",
        "Regras:",
        '1. Use "tool": null somente quando nenhuma ferramenta acima resolve a pergunta -- nesse caso responda '
        'em "answer", usando somente o Contexto abaixo.',
        '2. Quando uma ferramenta se aplica, preencha "tool" com o nome exato e "arguments" com os parametros '
        'que ela precisa. Deixe "answer" vazio.',
        "3. Nunca invente dados. Nunca diga que uma ferramenta rodou se voce nao a selecionou.",
    ]
    if context:
        lines += ["", "Contexto:", context]
    lines += ["", f"Pergunta: {question}", "", "JSON:"]
    return "\n".join(lines)


# Caps how much of a tool's result gets re-fed into the grounding prompt.
# Some real results (e.g. doctor's ~35 checks) serialize to ~1000+ tokens,
# which on constrained hardware (CPU-only Ollama) can push a single
# prompt-eval past two minutes -- the tool_result returned to the caller
# stays the full, real, untouched data; only what's shown to the *second*
# LLM call is capped, purely for latency.
_MAX_RESULT_CHARS = 1200


def build_result_prompt(question: str, tool_name: str, result: dict) -> str:
    serialized = json.dumps(result, ensure_ascii=False, default=str)
    if len(serialized) > _MAX_RESULT_CHARS:
        serialized = serialized[:_MAX_RESULT_CHARS] + " ... (resultado truncado por tamanho)"
    return (
        "Voce e o FlowCore. Uma ferramenta real foi executada e retornou o resultado abaixo.\n"
        "Escreva uma resposta em linguagem natural, em portugues do Brasil, para a pergunta original, "
        "usando SOMENTE os dados deste resultado. Nunca invente numeros ou fatos que nao estejam nele.\n\n"
        f"Pergunta original: {question}\n"
        f"Ferramenta executada: {tool_name}\n"
        f"Resultado: {serialized}\n\n"
        "Resposta:"
    )


def parse_tool_call(text: str) -> dict | None:
    """Extract the model's structured decision from its raw text.

    Returns None if no JSON object with a "tool" key could be found --
    callers treat that the same as an explicit tool=null (never a crash).
    Tolerates a ```json fenced block and/or stray text around the object,
    since not every model obeys "JSON only" perfectly.
    """
    candidate = text.strip()
    fenced = _CODE_FENCE_RE.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or "tool" not in parsed:
        return None
    return parsed
