"""Seed a small local dataset for testing Teólogos Chat RAG and memory."""

from __future__ import annotations

import asyncio

from storage import DocumentRepository, MemoryRepository


async def main() -> None:
    document_id = await DocumentRepository().insert(
        title="Fonte de teste — graça em Agostinho",
        content=(
            "Fonte local de demonstração para o Teólogos Chat. "
            "Agostinho de Hipona relaciona a graça à iniciativa divina, à cura da vontade "
            "e à transformação interior; esta fonte existe apenas para verificar a busca "
            "RAG e não substitui a leitura das obras originais."
        ),
        source="theology-demo",
    )
    memory = MemoryRepository().add(
        "Para o teste do Teólogos Chat, lembrar que a pergunta atual é sobre graça e Agostinho. #teologia #agostinho"
    )
    print(f"Documento inserido: {document_id}")
    print(f"Memória inserida: {memory['timestamp']}")
    print("Agora abra o app, configure a URL do Node e pergunte: Como Agostinho entende a graça?")


if __name__ == "__main__":
    asyncio.run(main())
