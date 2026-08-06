"""Tests for runtime.narrative.prompt (Sprint 25).

Core tier — pure string templating, no network.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _decision(
    priority=1, action="Reduzir duracao", urgency="HIGH", confidence=0.9, expected_impact="HIGH", products=None
):
    return {
        "priority": priority,
        "action": action,
        "urgency": urgency,
        "confidence": confidence,
        "expected_impact": expected_impact,
        "reason_chain": ["passo 1", "passo 2"],
        "recommended_products": products or [],
    }


def _report(
    decisions=None,
    overall_priority="HIGH",
    overall_confidence=0.8,
    top_risks=None,
    top_opportunities=None,
    overall_score=None,
):
    return {
        "overall_priority": overall_priority,
        "overall_confidence": overall_confidence,
        "decisions": decisions or [],
        "top_risks": top_risks or [],
        "top_opportunities": top_opportunities or [],
        "portfolio_score": {"overall": overall_score},
    }


class TestBuildPrompt:
    def test_includes_system_prompt(self):
        from runtime.narrative.prompt import SYSTEM_PROMPT, build_prompt

        prompt = build_prompt(_report())
        assert SYSTEM_PROMPT in prompt

    def test_includes_overall_priority_and_confidence(self):
        from runtime.narrative.prompt import build_prompt

        prompt = build_prompt(_report(overall_priority="CRITICAL", overall_confidence=0.95))
        assert "CRITICAL" in prompt
        assert "95%" in prompt

    def test_no_decisions_says_so_explicitly(self):
        from runtime.narrative.prompt import build_prompt

        prompt = build_prompt(_report(decisions=[]))
        assert "Nenhuma decisao material" in prompt

    def test_includes_each_decision_action_and_reason_chain(self):
        from runtime.narrative.prompt import build_prompt

        prompt = build_prompt(_report(decisions=[_decision(action="Aumentar liquidez em USD")]))
        assert "Aumentar liquidez em USD" in prompt
        assert "passo 1" in prompt
        assert "passo 2" in prompt

    def test_includes_products_when_present(self):
        from runtime.narrative.prompt import build_prompt

        products = [{"symbol": "SGOV", "name": "iShares 0-3 Month Treasury"}]
        prompt = build_prompt(_report(decisions=[_decision(products=products)]))
        assert "SGOV" in prompt

    def test_omits_products_line_when_absent(self):
        from runtime.narrative.prompt import build_prompt

        prompt = build_prompt(_report(decisions=[_decision(products=[])]))
        assert "Produtos sugeridos" not in prompt

    def test_includes_top_risks_and_opportunities_when_present(self):
        from runtime.narrative.prompt import build_prompt

        prompt = build_prompt(_report(top_risks=["risco A"], top_opportunities=["oportunidade B"]))
        assert "risco A" in prompt
        assert "oportunidade B" in prompt

    def test_includes_portfolio_score_when_available(self):
        from runtime.narrative.prompt import build_prompt

        prompt = build_prompt(_report(overall_score=72.5))
        assert "72.5" in prompt

    def test_omits_portfolio_score_line_when_insufficient_data(self):
        from runtime.narrative.prompt import build_prompt

        prompt = build_prompt(_report(overall_score=None))
        assert "Score geral do portfolio" not in prompt

    def test_deterministic_same_input_same_output(self):
        from runtime.narrative.prompt import build_prompt

        report = _report(decisions=[_decision()])
        assert build_prompt(report) == build_prompt(report)

    def test_never_instructs_model_to_invent_facts(self):
        from runtime.narrative.prompt import build_prompt

        prompt = build_prompt(_report())
        assert "nunca invente" in prompt.lower() or "nao invente" in prompt.lower()
