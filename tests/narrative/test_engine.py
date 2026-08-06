"""Tests for runtime.narrative.engine.NarrativeEngine (Sprint 25).

Core tier — Ollama calls are mocked (runtime/ollama.py's own coverage,
if any, is separate); these tests exercise the success/fallback branching
and the fallback narrative's own construction. Async calls driven via
asyncio.run(), matching this repo's established convention.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _decision(priority=1, action="Reduzir duracao", urgency="HIGH", confidence=0.9, expected_impact="HIGH"):
    return {
        "priority": priority,
        "action": action,
        "urgency": urgency,
        "confidence": confidence,
        "expected_impact": expected_impact,
        "reason_chain": ["passo 1", "passo 2"],
        "recommended_products": [],
    }


def _report(decisions=None, overall_priority="HIGH", overall_confidence=0.8):
    return {
        "overall_priority": overall_priority,
        "overall_confidence": overall_confidence,
        "decisions": decisions or [],
        "top_risks": [],
        "top_opportunities": [],
        "portfolio_score": {"overall": None},
    }


class TestGenerateSuccess:
    def test_llm_success_returns_llm_source(self):
        from runtime.narrative.engine import NarrativeEngine

        with (
            patch("runtime.narrative.engine.discover_ollama_endpoint", return_value="http://127.0.0.1:11434"),
            patch("runtime.narrative.engine.discover_default_model", return_value="qwen3:4b"),
            patch("runtime.narrative.engine.ollama_generate", return_value="  Uma narrativa gerada.  "),
        ):
            engine = NarrativeEngine()
            result = asyncio.run(engine.generate(1, _report(decisions=[_decision()])))

        assert result.source == "llm"
        assert result.model == "qwen3:4b"
        assert result.narrative == "Uma narrativa gerada."
        assert result.fallback_reason is None

    def test_prompt_is_built_from_the_decision_report(self):
        from runtime.narrative.engine import NarrativeEngine

        captured = {}

        def fake_generate(base_url, model, prompt, **kwargs):
            captured["prompt"] = prompt
            return "ok"

        with (
            patch("runtime.narrative.engine.discover_ollama_endpoint", return_value="http://x"),
            patch("runtime.narrative.engine.discover_default_model", return_value="m"),
            patch("runtime.narrative.engine.ollama_generate", side_effect=fake_generate),
        ):
            engine = NarrativeEngine()
            asyncio.run(engine.generate(1, _report(decisions=[_decision(action="Aumentar caixa em USD")])))

        assert "Aumentar caixa em USD" in captured["prompt"]


class TestGenerateFallback:
    def test_discovery_failure_falls_back(self):
        from runtime.narrative.engine import NarrativeEngine
        from runtime.ollama import OllamaDiscoveryError

        with patch(
            "runtime.narrative.engine.discover_ollama_endpoint", side_effect=OllamaDiscoveryError("no endpoint")
        ):
            engine = NarrativeEngine()
            result = asyncio.run(engine.generate(1, _report(decisions=[_decision()])))

        assert result.source == "fallback"
        assert result.model is None
        assert "no endpoint" in result.fallback_reason
        assert result.narrative  # non-empty

    def test_generation_failure_falls_back(self):
        from runtime.narrative.engine import NarrativeEngine
        from runtime.ollama import OllamaUnreachableError

        with (
            patch("runtime.narrative.engine.discover_ollama_endpoint", return_value="http://127.0.0.1:11434"),
            patch("runtime.narrative.engine.discover_default_model", return_value="qwen3:4b"),
            patch("runtime.narrative.engine.ollama_generate", side_effect=OllamaUnreachableError("down")),
        ):
            engine = NarrativeEngine()
            result = asyncio.run(engine.generate(1, _report(decisions=[_decision()])))

        assert result.source == "fallback"
        assert "down" in result.fallback_reason

    def test_fallback_narrative_reflects_the_decision_report(self):
        from runtime.narrative.engine import NarrativeEngine
        from runtime.ollama import OllamaUnreachableError

        with (
            patch("runtime.narrative.engine.discover_ollama_endpoint", side_effect=OllamaUnreachableError("down")),
        ):
            engine = NarrativeEngine()
            result = asyncio.run(
                engine.generate(
                    1, _report(decisions=[_decision(action="Aumentar liquidez em USD")], overall_priority="CRITICAL")
                )
            )

        assert "CRITICAL" in result.narrative
        assert "Aumentar liquidez em USD" in result.narrative
        assert "passo 1" in result.narrative

    def test_fallback_with_no_decisions_is_still_non_empty(self):
        from runtime.narrative.engine import NarrativeEngine
        from runtime.ollama import OllamaUnreachableError

        with patch("runtime.narrative.engine.discover_ollama_endpoint", side_effect=OllamaUnreachableError("down")):
            engine = NarrativeEngine()
            result = asyncio.run(engine.generate(1, _report(decisions=[])))

        assert result.narrative
        assert result.source == "fallback"

    def test_only_ollama_errors_are_caught_others_propagate(self):
        """A genuine bug (e.g. a KeyError from a malformed decision_report)
        must not be silently swallowed as a "fallback" -- only the
        documented OllamaError family triggers the graceful path."""
        from runtime.narrative.engine import NarrativeEngine

        with patch("runtime.narrative.engine.discover_ollama_endpoint", side_effect=RuntimeError("not an OllamaError")):
            engine = NarrativeEngine()
            try:
                asyncio.run(engine.generate(1, _report()))
                raised = False
            except RuntimeError:
                raised = True
        assert raised
