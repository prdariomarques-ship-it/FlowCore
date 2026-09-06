"""Structured Memory Manager (Short-Term, Episodic, Semantic) for FlowCore."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

STORAGE_DIR = Path(__file__).resolve().parent.parent.parent / "storage"
MEMORY_DIR = STORAGE_DIR / "memory"


class MemoryManager:
    def __init__(self, memory_dir: Path = MEMORY_DIR) -> None:
        self.memory_dir = memory_dir
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.short_term_file = self.memory_dir / "short_term.json"
        self.episodic_file = self.memory_dir / "episodic.json"
        self.semantic_file = self.memory_dir / "semantic.json"

        for f in [self.short_term_file, self.episodic_file, self.semantic_file]:
            if not f.exists():
                with open(f, "w", encoding="utf-8") as file:
                    json.dump([], file)

    def _read_file(self, file_path: Path) -> List[Dict[str, Any]]:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _write_file(self, file_path: Path, data: List[Dict[str, Any]]) -> None:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # Short-Term Memory: Execution context
    def set_short_term(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        items = self._read_file(self.short_term_file)
        # Remove existing key
        items = [i for i in items if i.get("key") != key]
        items.append({
            "key": key,
            "value": value,
            "created_at": time.time(),
            "expires_at": time.time() + ttl_seconds,
        })
        self._write_file(self.short_term_file, items)

    def get_short_term(self, key: str) -> Optional[Any]:
        items = self._read_file(self.short_term_file)
        now = time.time()
        for i in items:
            if i.get("key") == key:
                if i.get("expires_at", 0) > now:
                    return i.get("value")
        return None

    # Episodic Memory: What happened previously
    def add_episodic_event(self, agent_id: str, client_id: str, event_summary: str, details: Dict[str, Any]) -> Dict[str, Any]:
        episodes = self._read_file(self.episodic_file)
        entry = {
            "timestamp": time.time(),
            "agent_id": agent_id,
            "client_id": client_id,
            "summary": event_summary,
            "details": details,
        }
        episodes.append(entry)
        self._write_file(self.episodic_file, episodes)
        return entry

    def get_client_episodes(self, client_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        episodes = self._read_file(self.episodic_file)
        client_eps = [e for e in episodes if e.get("client_id") == client_id]
        return client_eps[-limit:]

    # Semantic Memory: Key persistent facts and preferences
    def set_semantic_fact(self, entity_id: str, fact_key: str, fact_value: Any) -> None:
        facts = self._read_file(self.semantic_file)
        facts = [f for f in facts if not (f.get("entity_id") == entity_id and f.get("fact_key") == fact_key)]
        facts.append({
            "entity_id": entity_id,
            "fact_key": fact_key,
            "fact_value": fact_value,
            "updated_at": time.time(),
        })
        self._write_file(self.semantic_file, facts)

    def get_semantic_facts(self, entity_id: str) -> Dict[str, Any]:
        facts = self._read_file(self.semantic_file)
        entity_facts = {}
        for f in facts:
            if f.get("entity_id") == entity_id:
                entity_facts[f.get("fact_key")] = f.get("fact_value")
        return entity_facts


_memory_instance = MemoryManager()

def get_memory_manager() -> MemoryManager:
    return _memory_instance
