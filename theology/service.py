"""Theology domain service built on FlowCore's shared RAG and LLM layers."""

from __future__ import annotations

from collections.abc import Iterable

from .catalog import get_periods, get_theologian, search_catalog


_MAX_HISTORY_MESSAGES = 12
_MAX_MESSAGE_CHARS = 1600
_MAX_SOURCE_CHARS = 5000


def list_periods() -> list[dict]:
    """Return the public catalog without exposing system prompts."""
    return [period.to_dict(include_prompts=False) for period in get_periods()]


def search(query: str, limit: int = 30) -> list[dict]:
    """Search historical people and periods in the local catalog."""
    return search_catalog(query, limit=limit)


def _format_sources(search_result: dict, recent_context: str) -> tuple[str, int, int, int, bool]:
    sections: list[str] = []
    source_count = 0
    document_count = 0
    memory_count = 0
    recent_context_used = bool(recent_context)

    documents = search_result.get("documents", [])
    if documents:
        sections.append("DOCUMENTOS ENCONTRADOS NO FLOWCORE:")
        for document in documents[:5]:
            title = str(document.get("title", "Documento"))
            content = str(document.get("content", ""))[:900]
            sections.append(f"[{title}]\n{content}")
            source_count += 1
            document_count += 1

    memories = search_result.get("memories", [])
    if memories:
        sections.append("MEMÓRIAS DO PESQUISADOR:")
        for memory in memories[:5]:
            text = str(memory.get("text", ""))[:700]
            sections.append(f"[Memória]\n{text}")
            source_count += 1
            memory_count += 1

    if recent_context:
        sections.append("CONTEXTO RECENTE DO ACERVO:")
        sections.append(recent_context[:1800])

    if not sections:
        return "Nenhum documento ou memória relevante foi encontrado no acervo local.", 0, 0, 0, recent_context_used
    return (
        "\n\n".join(sections)[:_MAX_SOURCE_CHARS],
        source_count,
        document_count,
        memory_count,
        recent_context_used,
    )


def _format_history(messages: Iterable[dict]) -> str:
    normalized: list[str] = []
    for message in list(messages)[-_MAX_HISTORY_MESSAGES:]:
        role = str(message.get("role", "user"))
        if role not in {"user", "assistant"}:
            continue
        content = str(message.get("content", "")).strip()[:_MAX_MESSAGE_CHARS]
        if content:
            label = "Pesquisador" if role == "user" else "Resposta anterior"
            normalized.append(f"{label}: {content}")
    return "\n".join(normalized) if normalized else "Nenhum histórico anterior."


def _build_prompt(theologian, question: str, history: str, sources: str) -> str:
    return f"""{theologian.prompt}

INTEGRAÇÃO COM O FLOWCORE
Você está respondendo dentro de uma ferramenta de pesquisa teológica. O FlowCore fornece o contexto abaixo a partir de documentos e memórias locais do pesquisador. Use-o quando for pertinente, mas não invente que uma fonte diz algo que não está no contexto.

FONTES E CONTEXTO LOCAL
{sources}

HISTÓRICO DA CONVERSA
{history}

NOVA PERGUNTA DO PESQUISADOR
{question}

Responda em português claro e estruturado. Distinga explicitamente entre reconstrução histórica, interpretação sua e informação presente nas fontes locais. Não fabrique citações literais, páginas ou referências bibliográficas. Se o acervo não for suficiente, diga o que está faltando e responda apenas dentro do que é historicamente defensável."""


async def respond(
    theologian_slug: str,
    question: str,
    messages: list[dict] | None = None,
    timeout: float | None = None,
) -> dict:
    """Answer as a historical theologian using FlowCore's local-first router."""
    theologian = get_theologian(theologian_slug)
    if theologian is None:
        raise ValueError("Teólogo não encontrado")

    clean_question = question.strip()
    if not clean_question:
        raise ValueError("A pergunta não pode estar vazia")
    if len(clean_question) > _MAX_MESSAGE_CHARS:
        raise ValueError(f"A pergunta deve ter no máximo {_MAX_MESSAGE_CHARS} caracteres")

    # Import lazily to avoid making the core service depend on the theology
    # package at import time and to keep this domain above the shared layer.
    import service as core_service

    search_result = await core_service.search(clean_question)
    recent_context = await core_service.build_rag_context(5)
    sources, source_count, document_count, memory_count, recent_context_used = _format_sources(
        search_result, recent_context
    )
    prompt = _build_prompt(theologian, clean_question, _format_history(messages or []), sources)
    response = await core_service.generate_prompt(
        prompt,
        timeout=timeout,
        max_tokens=1200,
        temperature=0.7,
        metadata={"purpose": "theology_chat"},
    )
    message = response.text.strip()
    if not message:
        raise ValueError("O modelo não retornou conteúdo")

    return {
        "message": message,
        "model": response.model,
        "provider": response.provider,
        "theologian": theologian.to_dict() | {"prompt": None},
        "source_count": source_count,
        "document_count": document_count,
        "memory_count": memory_count,
        "recent_context_used": recent_context_used,
    }
