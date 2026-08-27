"""Model Registry — tracks every AI model available to FlowCore.

Each entry records capabilities, cost, latency, and availability so the
router can make evidence-based decisions instead of hard-coded rules.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

_REGISTRY_FILE = Path.home() / ".flowcore" / "model_registry.json"

TASK_TYPES = (
    "chat",
    "analysis",
    "coding",
    "summarization",
    "market_brief",
    "classification",
    "vision",
    "thinking",
)


@dataclass
class ModelEntry:
    id: str
    provider: str                   # "ollama" | "openai_compat" | "anthropic"
    base_url: str
    capabilities: list[str]         # from TASK_TYPES + ["vision","tools","thinking"]
    parameter_size: str = ""
    quantization: str = ""
    context_length: int = 4096
    # Runtime stats (updated by benchmark engine)
    avg_latency_ms: float = 0.0
    avg_tokens_per_sec: float = 0.0
    success_rate: float = 1.0
    total_calls: int = 0
    total_failures: int = 0
    last_seen: float = field(default_factory=time.time)
    enabled: bool = True
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ModelEntry":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class ModelRegistry:
    """Persistent registry of AI models available to FlowCore."""

    def __init__(self, path: Path = _REGISTRY_FILE) -> None:
        self._path = path
        self._models: dict[str, ModelEntry] = {}
        self._load()

    # ── persistence ─────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                self._models = {k: ModelEntry.from_dict(v) for k, v in data.items()}
            except Exception:
                self._models = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(
            {k: v.to_dict() for k, v in self._models.items()},
            indent=2, ensure_ascii=False,
        ))

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def register(self, entry: ModelEntry) -> None:
        self._models[entry.id] = entry
        self._save()

    def update_stats(
        self,
        model_id: str,
        *,
        latency_ms: float,
        tokens_per_sec: float = 0.0,
        success: bool = True,
    ) -> None:
        entry = self._models.get(model_id)
        if entry is None:
            return
        n = entry.total_calls
        # exponential moving average (α=0.2 for new, settled after ~5 calls)
        alpha = min(0.5, 1 / max(1, n))
        entry.avg_latency_ms = entry.avg_latency_ms * (1 - alpha) + latency_ms * alpha
        if tokens_per_sec:
            entry.avg_tokens_per_sec = entry.avg_tokens_per_sec * (1 - alpha) + tokens_per_sec * alpha
        entry.total_calls += 1
        if not success:
            entry.total_failures += 1
        entry.success_rate = 1 - entry.total_failures / max(1, entry.total_calls)
        entry.last_seen = time.time()
        self._save()

    def get(self, model_id: str) -> ModelEntry | None:
        return self._models.get(model_id)

    def list_all(self) -> list[ModelEntry]:
        return list(self._models.values())

    def list_capable(self, task: str) -> list[ModelEntry]:
        """Return enabled models that support the given task type."""
        return [m for m in self._models.values() if m.enabled and task in m.capabilities]

    def remove(self, model_id: str) -> bool:
        if model_id in self._models:
            del self._models[model_id]
            self._save()
            return True
        return False

    # ── sync from Ollama ─────────────────────────────────────────────────────

    def sync_from_ollama(self, ollama_url: str) -> list[str]:
        """Pull available models from Ollama and upsert into registry."""
        import urllib.request
        try:
            req = urllib.request.urlopen(f"{ollama_url.rstrip('/')}/api/tags", timeout=10)
            data = json.loads(req.read())
        except Exception:
            return []

        synced: list[str] = []
        for m in data.get("models", []):
            name = m.get("name", "")
            if not name:
                continue
            details = m.get("details", {})
            caps = ["chat", "analysis", "summarization", "market_brief", "classification"]
            if "thinking" in m.get("capabilities", []):
                caps.append("thinking")
            if "tools" in m.get("capabilities", []):
                caps.append("coding")
            if "vision" in m.get("capabilities", []):
                caps.append("vision")
            existing = self._models.get(name)
            entry = ModelEntry(
                id=name,
                provider="ollama",
                base_url=ollama_url,
                capabilities=caps,
                parameter_size=details.get("parameter_size", ""),
                quantization=details.get("quantization_level", ""),
                context_length=details.get("context_length", 4096),
                # preserve stats if model already exists
                avg_latency_ms=existing.avg_latency_ms if existing else 0.0,
                avg_tokens_per_sec=existing.avg_tokens_per_sec if existing else 0.0,
                success_rate=existing.success_rate if existing else 1.0,
                total_calls=existing.total_calls if existing else 0,
                total_failures=existing.total_failures if existing else 0,
                last_seen=time.time(),
                enabled=existing.enabled if existing else True,
            )
            self._models[name] = entry
            synced.append(name)
        if synced:
            self._save()
        return synced


_registry: ModelRegistry | None = None


def get_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
