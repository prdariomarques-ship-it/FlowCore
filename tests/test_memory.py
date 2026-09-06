"""Tests for MemoryManager (Short-Term, Episodic, Semantic)."""

import pytest
from runtime.memory.manager import MemoryManager

def test_memory_manager(tmp_path):
    mem_dir = tmp_path / "memory"
    mgr = MemoryManager(memory_dir=mem_dir)

    # Short Term
    mgr.set_short_term("temp_context", {"step": 1}, ttl_seconds=60)
    assert mgr.get_short_term("temp_context") == {"step": 1}

    # Episodic
    mgr.add_episodic_event("follow_up_agent", "cli_001", "Contacted client", {"channel": "whatsapp"})
    eps = mgr.get_client_episodes("cli_001")
    assert len(eps) == 1
    assert eps[0]["summary"] == "Contacted client"

    # Semantic
    mgr.set_semantic_fact("cli_001", "preferred_contact_time", "morning")
    facts = mgr.get_semantic_facts("cli_001")
    assert facts["preferred_contact_time"] == "morning"
