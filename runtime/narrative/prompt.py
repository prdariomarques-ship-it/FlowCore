"""Prompt construction (Sprint 25).

The prompt is built entirely from an already-computed DecisionReport
dict (service.portfolio_decision()'s output) -- no free-text user input,
no new facts introduced here. This keeps every LLM call fully auditable:
whatever the model was given is exactly what's in the DecisionReport,
nothing hidden, nothing injected. The Narrative Engine sits strictly
downstream of the deterministic Decision Engine (Layer 5) -- it narrates
an already-final decision, it never influences one.
"""

from __future__ import annotations

__all__ = ["SYSTEM_PROMPT", "build_prompt"]

SYSTEM_PROMPT = (
    "Voce e um assistente que traduz um relatorio de decisao de portfolio, ja "
    "calculado por um motor deterministico, em uma narrativa clara e natural "
    "em portugues do Brasil, para um investidor pessoa fisica.\n"
    "Regras estritas:\n"
    "1) Nunca invente numeros, ativos ou recomendacoes que nao estejam no relatorio abaixo.\n"
    "2) Nunca sugira uma acao que nao esteja explicitamente listada no relatorio.\n"
    "3) Seja claro e direto, organizando por prioridade (mais urgente primeiro).\n"
    "4) Nao adicione avisos legais nem se refira a si mesmo como IA."
)


def build_prompt(decision_report: dict) -> str:
    priority = decision_report["overall_priority"]
    conf = decision_report["overall_confidence"]
    lines = [SYSTEM_PROMPT, "", "Relatorio:", f"Prioridade geral: {priority} (confianca {conf:.0%})"]

    top_risks = decision_report.get("top_risks") or []
    top_opportunities = decision_report.get("top_opportunities") or []
    if top_risks:
        lines.append(f"Principais riscos: {', '.join(top_risks)}")
    if top_opportunities:
        lines.append(f"Principais oportunidades: {', '.join(top_opportunities)}")

    decisions = decision_report.get("decisions") or []
    if not decisions:
        lines.append("Nenhuma decisao material identificada no momento.")
    for d in decisions:
        lines.append("")
        header = f"[{d['priority']}] {d['action']} (urgencia={d['urgency']}, confianca={d['confidence']:.0%}"
        lines.append(f"{header}, impacto={d['expected_impact']})")
        lines.append(f"Motivo: {' '.join(d.get('reason_chain') or [])}")
        products = d.get("recommended_products") or []
        if products:
            lines.append(f"Produtos sugeridos: {', '.join(p['symbol'] for p in products)}")

    score = decision_report.get("portfolio_score") or {}
    if score.get("overall") is not None:
        lines.append("")
        lines.append(f"Score geral do portfolio: {score['overall']:.1f}/100")

    lines.append("")
    lines.append("Escreva agora a narrativa (2 a 4 paragrafos, em portugues do Brasil):")
    return "\n".join(lines)
