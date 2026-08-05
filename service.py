"""FlowCore Service Layer.

Business logic shared by the CLI (flowcore.py), FastAPI (api/router.py),
and MCP (mcp_server.py) interfaces, so the same operation is never
implemented three times. Sprint 14, priority 1, task 2.

This layer never prints, never raises HTTPException, never formats an
MCP response — it returns plain values and lets OllamaError/ValueError
propagate. Each interface catches what it needs and presents it in its
own idiom (CLI prints colored text, FastAPI maps to HTTP status codes,
MCP raises RuntimeError).
"""

from __future__ import annotations

import asyncio

from runtime.ollama import (
    discover_default_model,
    discover_ollama_endpoint,
    generate as ollama_generate,
)
from storage import DocumentRepository, MemoryRepository

_doc_repo = DocumentRepository()
_mem_repo = MemoryRepository()

# Canonical note/todo/agenda title labels. Previously CLI/MCP used
# "Note"/"TODO"/"Agenda" while api/router.py separately used
# "Nota"/"TODO"/"Agenda" for the same operation — picked one.
NOTE_KIND_LABELS = {"note": "Note", "todo": "TODO", "agenda": "Agenda"}


async def add_note(text: str, kind: str = "note") -> dict:
    """Create a note/todo/agenda document. Raises ValueError for an unknown kind."""
    if kind not in NOTE_KIND_LABELS:
        raise ValueError(f"kind must be one of {sorted(NOTE_KIND_LABELS)}, got {kind!r}")
    doc_id = await _doc_repo.insert(NOTE_KIND_LABELS[kind], text, kind)
    return {"id": doc_id, "kind": kind, "text": text}


async def list_notes(kind: str | None = None) -> list[dict]:
    """List note/todo/agenda documents, optionally filtered by kind."""
    docs = await _doc_repo.list_all()
    return [d for d in docs if d.get("source") in NOTE_KIND_LABELS and (kind is None or d.get("source") == kind)]


async def build_rag_context(limit: int = 5) -> str:
    """Build a prompt-ready context string from the N most recent documents.

    Degrades to no context (rather than failing the whole ask) if listing
    documents itself errors — grounding is a nice-to-have, not a hard
    requirement for the model to answer at all.
    """
    try:
        recent_docs = await _doc_repo.list_recent(limit)
    except Exception:
        recent_docs = []
    if not recent_docs:
        return ""
    context = "Context from documents:\n"
    for doc in recent_docs:
        context += f"\n[{doc['title']}]\n{doc['content'][:300]}\n"
    return context


async def ask(question: str, timeout: float | None = None) -> tuple[str, str]:
    """RAG-grounded ask: resolve endpoint/model, ground with recent documents,
    generate. Returns (answer, model). Raises OllamaDiscoveryError (endpoint/
    model resolution) or an OllamaError subclass (generation) on failure —
    callers decide how to present it.
    """
    base_url = discover_ollama_endpoint()
    model = discover_default_model()
    context = await build_rag_context(5)

    system_prompt = "You are a helpful AI assistant. Use the provided context to answer questions accurately."
    prompt = f"{system_prompt}\n\nContext:\n{context}\n\nQuestion: {question}\n\nAnswer:"

    kwargs = {"timeout": timeout} if timeout is not None else {}
    # generate() blocks (network I/O + warm-up polling); run off the event
    # loop thread so FastAPI/MCP stay responsive to other requests. Harmless
    # for the CLI's single-coroutine asyncio.run() too.
    answer = await asyncio.to_thread(ollama_generate, base_url, model, prompt, **kwargs)
    return answer, model
