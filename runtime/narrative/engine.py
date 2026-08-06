"""NarrativeEngine (Sprint 25) -- the ONLY layer in FlowCore's SCPX
pipeline allowed to call an LLM, and even then strictly as a
presentation step over an already-fully-computed DecisionReport. Never
consulted by, and never feeds back into, any earlier layer -- the
Decision Engine (Layer 5) runs to completion with zero awareness this
layer exists, exactly the "LLM as presentation/narrative layer only,
never inside the decision pipeline" rule.

Degrades gracefully: if Ollama is unreachable, the model isn't
installed, or generation times out (any OllamaError subclass -- see
runtime/ollama.py), returns a deterministic fallback narrative (built
from the same DecisionReport's reason chains, no LLM) instead of
raising. "The system must remain deterministic" is the base guarantee;
LLM narrative is a strict, optional enhancement on top -- unlike
service.ask() (the Chat feature), where the LLM *is* the feature and an
OllamaError is correctly surfaced to the caller, here there's always a
deterministic reason_chain already computed to fall back to.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from runtime.narrative.models import NarrativeReport
from runtime.narrative.prompt import build_prompt
from runtime.ollama import OllamaError, discover_default_model, discover_ollama_endpoint
from runtime.ollama import generate as ollama_generate

__all__ = ["NarrativeEngine"]


def _fallback_narrative(decision_report: dict) -> str:
    decisions = decision_report.get("decisions") or []
    if not decisions:
        return "Nenhuma decisao material identificada no momento para este portfolio."
    priority = decision_report["overall_priority"]
    conf = decision_report["overall_confidence"]
    parts = [f"Prioridade geral: {priority} (confianca {conf:.0%})."]
    for d in decisions:
        parts.append(
            f"#{d['priority']} {d['action']} (urgencia {d['urgency']}, confianca {d['confidence']:.0%}). "
            f"{' '.join(d.get('reason_chain') or [])}"
        )
    return "\n\n".join(parts)


class NarrativeEngine:
    async def generate(self, portfolio_id: int, decision_report: dict, timeout: float | None = None) -> NarrativeReport:
        now = datetime.now(UTC).isoformat()
        try:
            base_url = await asyncio.to_thread(discover_ollama_endpoint)
            model = await asyncio.to_thread(discover_default_model)
            prompt = build_prompt(decision_report)
            kwargs = {"timeout": timeout} if timeout is not None else {}
            text = await asyncio.to_thread(ollama_generate, base_url, model, prompt, **kwargs)
            return NarrativeReport(
                portfolio_id=portfolio_id,
                narrative=text.strip(),
                source="llm",
                model=model,
                fallback_reason=None,
                generated_at=now,
            )
        except OllamaError as e:
            return NarrativeReport(
                portfolio_id=portfolio_id,
                narrative=_fallback_narrative(decision_report),
                source="fallback",
                model=None,
                fallback_reason=str(e),
                generated_at=now,
            )
