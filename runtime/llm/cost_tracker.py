"""Cost tracker and token metrics recorder for FlowCore LLM execution."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List

STORAGE_DIR = Path(__file__).resolve().parent.parent.parent / "storage"
COST_FILE = STORAGE_DIR / "llm_costs.json"

# Pricing per 1M tokens in USD (DeepSeek & defaults)
PRICING_PER_1M = {
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "deepseek-coder": {"input": 0.14, "output": 0.28},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "ollama": {"input": 0.0, "output": 0.0},
    "default": {"input": 0.20, "output": 0.40},
}


class CostTracker:
    def __init__(self, storage_file: Path = COST_FILE) -> None:
        self.storage_file = storage_file
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.storage_file.exists():
            self._save({"total_cost_usd": 0.0, "total_tokens": 0, "calls": []})

    def _load(self) -> Dict[str, Any]:
        try:
            with open(self.storage_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"total_cost_usd": 0.0, "total_tokens": 0, "calls": []}

    def _save(self, data: Dict[str, Any]) -> None:
        with open(self.storage_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def calculate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        rates = PRICING_PER_1M.get(model.lower(), PRICING_PER_1M["default"])
        input_cost = (prompt_tokens / 1_000_000.0) * rates["input"]
        output_cost = (completion_tokens / 1_000_000.0) * rates["output"]
        return round(input_cost + output_cost, 6)

    def record_call(
        self,
        agent_id: str,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float = 0.0,
    ) -> Dict[str, Any]:
        cost = self.calculate_cost(model, prompt_tokens, completion_tokens)
        total_tokens = prompt_tokens + completion_tokens

        data = self._load()
        data["total_cost_usd"] = round(data.get("total_cost_usd", 0.0) + cost, 6)
        data["total_tokens"] = data.get("total_tokens", 0) + total_tokens

        entry = {
            "timestamp": time.time(),
            "agent_id": agent_id,
            "provider": provider,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_usd": cost,
            "latency_ms": latency_ms,
        }

        data.setdefault("calls", []).append(entry)
        self._save(data)
        return entry

    def get_summary(self) -> Dict[str, Any]:
        data = self._load()
        calls = data.get("calls", [])

        # Summary per agent
        by_agent: Dict[str, Dict[str, Any]] = {}
        by_model: Dict[str, Dict[str, Any]] = {}

        for call in calls:
            ag = call.get("agent_id", "unknown")
            md = call.get("model", "unknown")
            cost = call.get("cost_usd", 0.0)
            tokens = call.get("total_tokens", 0)

            if ag not in by_agent:
                by_agent[ag] = {"calls": 0, "cost_usd": 0.0, "tokens": 0}
            by_agent[ag]["calls"] += 1
            by_agent[ag]["cost_usd"] = round(by_agent[ag]["cost_usd"] + cost, 6)
            by_agent[ag]["tokens"] += tokens

            if md not in by_model:
                by_model[md] = {"calls": 0, "cost_usd": 0.0, "tokens": 0}
            by_model[md]["calls"] += 1
            by_model[md]["cost_usd"] = round(by_model[md]["cost_usd"] + cost, 6)
            by_model[md]["tokens"] += tokens

        return {
            "total_cost_usd": data.get("total_cost_usd", 0.0),
            "total_tokens": data.get("total_tokens", 0),
            "total_calls": len(calls),
            "by_agent": by_agent,
            "by_model": by_model,
        }


_tracker_instance = CostTracker()

def get_cost_tracker() -> CostTracker:
    return _tracker_instance
