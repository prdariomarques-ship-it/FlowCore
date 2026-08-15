from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from theology.catalog import get_all_theologians, get_periods, get_theologian, search_catalog
from theology.service import respond


def test_catalog_contains_expected_historical_scope():
    assert len(get_periods()) == 12
    assert len(get_all_theologians()) == 93
    assert get_theologian("paulo-de-tarso").name == "Paulo de Tarso"
    assert get_theologian("karl-barth").name == "Karl Barth"
    assert get_theologian("agostinho-de-hipona").name == "Agostinho de Hipona"


def test_catalog_search_matches_name_tradition_and_period():
    by_name = search_catalog("Agostinho")
    assert by_name[0]["slug"] == "agostinho-de-hipona"

    by_tradition = search_catalog("reformada genebra")
    assert {item["slug"] for item in by_tradition} >= {"joao-calvino", "francis-turretin"}


def test_theology_response_uses_rag_memory_and_historical_prompt():
    captured: dict[str, str] = {}

    async def fake_search(query: str) -> dict:
        assert query == "Como Agostinho entende a graça?"
        return {
            "documents": [{"title": "Notas sobre graça", "content": "A graça é dom imerecido."}],
            "memories": [{"text": "Pesquisar a relação entre graça e vontade."}],
        }

    async def fake_recent_context(limit: int) -> str:
        assert limit == 5
        return "Contexto recente sobre a tradição agostiniana."

    async def fake_generate(prompt: str, **kwargs):
        captured["prompt"] = prompt
        assert kwargs["metadata"] == {"purpose": "theology_chat"}
        assert kwargs["max_tokens"] == 1200
        return type("Response", (), {"text": "A resposta fundamentada.", "model": "test-model", "provider": "test"})()

    with patch("service.search", new=AsyncMock(side_effect=fake_search)), patch(
        "service.build_rag_context", new=AsyncMock(side_effect=fake_recent_context)
    ), patch("service.generate_prompt", new=AsyncMock(side_effect=fake_generate)):
        result = asyncio.run(
            respond(
                "agostinho-de-hipona",
                "Como Agostinho entende a graça?",
                messages=[{"role": "user", "content": "Quero estudar a graça."}],
            )
        )

    assert result["message"] == "A resposta fundamentada."
    assert result["model"] == "test-model"
    assert result["provider"] == "test"
    assert result["source_count"] == 2
    assert result["document_count"] == 1
    assert result["memory_count"] == 1
    assert result["recent_context_used"] is True
    assert "Agostinho" in captured["prompt"]
    assert "Notas sobre graça" in captured["prompt"]
    assert "MEMÓRIAS DO PESQUISADOR" in captured["prompt"]
    assert "Quero estudar a graça." in captured["prompt"]


def test_theology_api_catalog_search_and_response():
    from fastapi.testclient import TestClient
    from api.router import create_app

    client = TestClient(create_app(version="test", platform_info={"os_name": "test"}))
    periods_response = client.get("/api/theology/periods")
    assert periods_response.status_code == 200
    assert len(periods_response.json()["periods"]) == 12

    search_response = client.get("/api/theology/search", params={"q": "graça"})
    assert search_response.status_code == 200
    assert any(item["slug"] == "agostinho-de-hipona" for item in search_response.json()["results"])

    fake_result = {
        "message": "Resposta de teste.",
        "model": "test-model",
        "provider": "test",
        "theologian": {"slug": "agostinho-de-hipona", "name": "Agostinho de Hipona"},
        "source_count": 1,
        "document_count": 1,
        "memory_count": 0,
        "recent_context_used": False,
    }
    with patch("theology.service.respond", new=AsyncMock(return_value=fake_result)):
        response = client.post(
            "/api/theology/respond",
            json={
                "theologian_slug": "agostinho-de-hipona",
                "messages": [{"role": "user", "content": "Explique a graça."}],
            },
        )
    assert response.status_code == 200
    assert response.json()["message"] == "Resposta de teste."
    assert response.json()["source_count"] == 1
    assert response.json()["document_count"] == 1
    assert response.json()["memory_count"] == 0
    assert response.json()["recent_context_used"] is False
