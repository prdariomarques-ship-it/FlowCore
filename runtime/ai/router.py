"""Model Router — selects the best model for each task type.

Routing policy (in order):
1. If a model is pinned for the task in routing_rules.json, use it.
2. Otherwise pick the enabled model for the task with highest success_rate,
   breaking ties by lowest avg_latency_ms.
3. Fall back to the globally configured model in ai.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model_registry import ModelEntry, get_registry, TASK_TYPES

_RULES_FILE = Path.home() / ".flowcore" / "routing_rules.json"
_AI_CONFIG   = Path.home() / ".flowcore" / "ai.json"

_DEFAULT_RULES: dict[str, str] = {}


def _load_ai_cfg() -> dict[str, Any]:
    if _AI_CONFIG.exists():
        try:
            return json.loads(_AI_CONFIG.read_text())
        except Exception:
            pass
    return {}


class ModelRouter:
    """Routes task types to the most suitable available model."""

    def __init__(self) -> None:
        self._rules: dict[str, str] = {}
        self._load_rules()

    def _load_rules(self) -> None:
        if _RULES_FILE.exists():
            try:
                self._rules = json.loads(_RULES_FILE.read_text())
            except Exception:
                self._rules = {}

    def _save_rules(self) -> None:
        _RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        _RULES_FILE.write_text(json.dumps(self._rules, indent=2, ensure_ascii=False))

    def pin(self, task: str, model_id: str) -> None:
        """Pin a specific model for a task type."""
        if task not in TASK_TYPES:
            raise ValueError(f"Unknown task type: {task}. Must be one of {TASK_TYPES}")
        self._rules[task] = model_id
        self._save_rules()

    def unpin(self, task: str) -> None:
        self._rules.pop(task, None)
        self._save_rules()

    def get_rules(self) -> dict[str, str]:
        self._load_rules()
        return dict(self._rules)

    def select(self, task: str = "chat") -> ModelEntry | None:
        """Return the best ModelEntry for the given task, or None if unavailable."""
        self._load_rules()
        registry = get_registry()

        # 1. Pinned rule
        pinned_id = self._rules.get(task)
        if pinned_id:
            entry = registry.get(pinned_id)
            if entry and entry.enabled:
                return entry

        # 2. Best by success_rate → latency
        candidates = registry.list_capable(task)
        if candidates:
            return min(
                candidates,
                key=lambda m: (-m.success_rate, m.avg_latency_ms),
            )

        # 3. Fallback: global configured model
        cfg = _load_ai_cfg()
        fallback_id = cfg.get("model", "")
        if fallback_id:
            entry = registry.get(fallback_id)
            if entry and entry.enabled:
                return entry

        # 4. Any enabled model
        all_enabled = [m for m in registry.list_all() if m.enabled]
        return all_enabled[0] if all_enabled else None

    def routing_table(self) -> list[dict]:
        """Return the full routing table for all task types."""
        self._load_rules()
        rows = []
        for task in TASK_TYPES:
            entry = self.select(task)
            rows.append({
                "task": task,
                "model_id": entry.id if entry else None,
                "provider": entry.provider if entry else None,
                "pinned": task in self._rules,
                "success_rate": entry.success_rate if entry else None,
                "avg_latency_ms": entry.avg_latency_ms if entry else None,
            })
        return rows


_router: ModelRouter | None = None


def get_router() -> ModelRouter:
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router
