"""NarrativeEngine (Sprint 25, migrated to the LLM Router after its
introduction) -- the ONLY layer in FlowCore's SCPX pipeline allowed to
call an LLM, and even then strictly as a presentation step over an
already-fully-computed DecisionReport. Never consulted by, and never
feeds back into, any earlier layer -- the Decision Engine (Layer 5) runs
to completion with zero awareness this layer exists, exactly the "LLM as
presentation/narrative layer only, never inside the decision pipeline"
rule.

Depends only on runtime/llm/'s generic LLMRouter -- it never imports
runtime/ollama.py or any other provider-specific module. service.py (the
composition root) constructs the Router and injects it here, exactly
like every other engine in this codebase receives its dependencies
(ImpactEngine(regime_engine), DecisionEngine(impact_engine,
exposure_engine), ...).

Degrades gracefully: on any LLMError (no provider available, all
providers failed, budget exceeded, ...), returns a deterministic
fallback narrative (built from the same DecisionReport's reason chains,
no LLM) instead of raising. "The system must remain deterministic" is
the base guarantee; LLM narrative is a strict, optional enhancement on
top -- unlike service.ask() (the Chat feature), where the LLM *is* the
feature and an error is correctly surfaced to the caller, here there's
always a deterministic reason_chain already computed to fall back to.

Requests are never allowed to leave the machine: LLMRequest.metadata
never sets "allow_cloud" here, so runtime/llm/policy.py's LocalFirstPolicy
structurally excludes cloud providers for every narrative request,
regardless of what's configured in the registry.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from runtime.llm import LLMError, LLMRequest, LLMRouter
from runtime.narrative.models import NarrativeReport
from runtime.narrative.prompt import build_prompt

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
    def __init__(self, router: LLMRouter) -> None:
        self._router = router

    async def generate(self, portfolio_id: int, decision_report: dict, timeout: float | None = None) -> NarrativeReport:
        now = datetime.now(UTC).isoformat()
        prompt = build_prompt(decision_report)
        request = LLMRequest(
            prompt=prompt, timeout=timeout, metadata={"purpose": "narrative", "portfolio_id": portfolio_id}
        )
        try:
            response = await asyncio.to_thread(self._router.generate, request)
            return NarrativeReport(
                portfolio_id=portfolio_id,
                narrative=response.text.strip(),
                source="llm",
                model=response.model,
                fallback_reason=None,
                generated_at=now,
            )
        except LLMError as e:
            return NarrativeReport(
                portfolio_id=portfolio_id,
                narrative=_fallback_narrative(decision_report),
                source="fallback",
                model=None,
                fallback_reason=str(e),
                generated_at=now,
            )
