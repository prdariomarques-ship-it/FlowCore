"""FlowCore — MCP stdio server.

Exposes memory/document commands (remember, recall, note, todo, agenda,
search, ...) as MCP tools so an MCP client (e.g. Claude Code) can call
FlowCore directly instead of shelling out to the CLI.

Started via: python3 flowcore.py mcp
"""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

import service
from runtime.ollama import OllamaError
from storage import DocumentRepository, MemoryRepository

ROOT = Path(__file__).resolve().parent

mcp = FastMCP("flowcore")

_doc_repo = DocumentRepository()
_mem_repo = MemoryRepository()


@mcp.tool()
def flowcore_remember(text: str) -> dict:
    """Save a memory. Use '#topic' words in the text to tag it."""
    memory = _mem_repo.add(text)
    return {"saved": True, "topics": memory.get("topics", [])}


@mcp.tool()
def flowcore_recall(topic: str) -> list[dict]:
    """Recall memories matching a topic or keyword (case-insensitive substring)."""
    return _mem_repo.search(topic)


@mcp.tool()
def flowcore_memories() -> list[dict]:
    """List all saved memories."""
    return _mem_repo.list_all()


@mcp.tool()
async def flowcore_docs() -> list[dict]:
    """List all imported documents (id, title, source, created_at)."""
    return await _doc_repo.list_all()


@mcp.tool()
async def flowcore_show(doc_id: int) -> dict:
    """Show a document's full content by its numeric ID."""
    doc = await _doc_repo.get_by_id(doc_id)
    if not doc:
        raise ValueError(f"Document not found: {doc_id}")
    return doc


@mcp.tool()
async def flowcore_import_markdown(filepath: str) -> dict:
    """Import a Markdown file into FlowCore's document store."""
    path = Path(filepath).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    content = path.read_text(encoding="utf-8")
    title = path.stem
    for line in content.split("\n"):
        if line.startswith("# "):
            title = line[2:].strip()
            break
    doc_id = await _doc_repo.insert(title, content, str(path))
    return {"id": doc_id, "title": title, "chars": len(content)}


@mcp.tool()
async def flowcore_search(query: str) -> dict:
    """Search both documents and memories for a query string."""
    return {
        "documents": await _doc_repo.search(query),
        "memories": _mem_repo.search(query),
    }


@mcp.tool()
async def flowcore_daily_summary() -> dict:
    """Get today's summary: document/memory/task counts and recent documents."""
    return {
        "documents": await _doc_repo.count(),
        "memories": _mem_repo.count(),
        "tasks": await _doc_repo.count_by_source("note", "todo", "agenda"),
        "recent_documents": await _doc_repo.list_recent(5),
    }


@mcp.tool()
async def flowcore_stats() -> dict:
    """Get FlowCore statistics (document count, memory count)."""
    return {
        "documents": await _doc_repo.count(),
        "memories": _mem_repo.count(),
    }


@mcp.tool()
async def flowcore_note(text: str) -> dict:
    """Add a quick note."""
    result = await service.add_note(text, "note")
    return {"id": result["id"], "saved": True}


@mcp.tool()
async def flowcore_todo(task: str) -> dict:
    """Add a TODO item."""
    result = await service.add_note(task, "todo")
    return {"id": result["id"], "saved": True}


@mcp.tool()
async def flowcore_agenda(event: str) -> dict:
    """Add an event to the agenda."""
    result = await service.add_note(event, "agenda")
    return {"id": result["id"], "saved": True}


@mcp.tool()
async def flowcore_ask(question: str, timeout: float | None = None) -> str:
    """Ask the local Ollama model a question, grounded with the 5 most recent documents as context.

    Warms up the model first if it's not already loaded in Ollama (can take
    a while on first call). `timeout` overrides FLOWCORE_OLLAMA_TIMEOUT
    (default 180s) for both the warm-up wait and the generate call.
    """
    try:
        answer, _model = await service.ask(question, timeout=timeout)
        return answer
    except OllamaError as e:
        raise RuntimeError(str(e)) from e


def run() -> None:
    mcp.run(transport="stdio")
