"""Tests for agents/orchestrator.py -- CoreOrchestrator's classify ->
context -> reason -> decide -> execute -> record loop.

No pytest-asyncio dependency in this project -- each test wraps its
async body in asyncio.run(). CoreOrchestrator internally instantiates
ClientRepository/TenantRepository/AgentEventRepository with their default
(real, shared) db path -- same as production -- so these tests run
against the real data/flowcore.db, relying on TenantRepository's
random-hex office_id (like the rest of this suite's API-level tests, see
tests/_auth_helper.py) for isolation rather than a per-test database.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.events import AgentEvent  # noqa: E402
from agents.orchestrator import CoreOrchestrator  # noqa: E402
from storage.agent_event_repo import AgentEventRepository  # noqa: E402
from storage.client_repo import ClientRepository  # noqa: E402
from storage.tenant_repo import TenantRepository  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class _FakeLLMResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeLLMRouter:
    def __init__(self, text: str = "Reasoning gerado pelo modelo.") -> None:
        self._text = text
        self.calls: list = []

    def generate(self, request):
        self.calls.append(request)
        return _FakeLLMResponse(self._text)


class _FailingLLMRouter:
    def generate(self, request):
        raise RuntimeError("provider unavailable")


async def _office_with_client_and_violation(telegram_chat_id: str | None = "-100999"):
    """A real office, a real client with a real compliance violation
    passed as the event payload (as the observation loop that publishes
    these events would build it), and a Telegram destination configured
    (unless the caller wants to exercise the not-configured path)."""
    tenant_repo = TenantRepository()
    client_repo = ClientRepository()
    office = await tenant_repo.create_office("Escritório Teste Orchestrator")
    if telegram_chat_id:
        await tenant_repo.set_telegram_chat_id(office["id"], telegram_chat_id)
    await client_repo.seed_office(office["id"], with_demo_clients=True)
    clients = await client_repo.list_clients(office["id"])
    client = next(c for c in clients if c["id"] == "demo-client-21")  # Junqueira Capital, out of band
    event = AgentEvent(
        type="PORTFOLIO_OUT_OF_PROFILE", source="compliance_agent",
        entity={"kind": "client", "id": client["id"]},
        payload={"message": "Renda Fixa Total 2.0 p.p. acima do limite (67.0% vs 65.0%)."},
        priority="HIGH",
    )
    return office, client, event


class TestUnhandledEventType:
    def test_unknown_event_type_is_recorded_as_ignored_not_silently_dropped(self):
        async def scenario():
            tenant_repo = TenantRepository()
            office = await tenant_repo.create_office("Escritório Teste Ignore")
            event = AgentEvent(type="SOMETHING_NEW", source="x", entity={"kind": "client", "id": "c1"})
            published = await AgentEventRepository().publish(office["id"], event)
            orchestrator = CoreOrchestrator()
            return await orchestrator.handle_event(office["id"], published)

        result = _run(scenario())
        assert result["status"] == "ignored"
        assert "SOMETHING_NEW" in result["decision"]["reason"]


class TestPortfolioOutOfProfile:
    def test_end_to_end_with_llm_reasoning_and_telegram_sent(self):
        fake_router = _FakeLLMRouter("Explicação real gerada pelo modelo.")
        sent = {}

        def fake_send_message(text, chat_id=None, timeout=10):
            sent["text"] = text
            sent["chat_id"] = chat_id
            return {"ok": True}

        async def scenario():
            office, client, event = await _office_with_client_and_violation()
            published = await AgentEventRepository().publish(office["id"], event)
            orchestrator = CoreOrchestrator(llm_router=fake_router)
            with patch("runtime.telegram.send_message", side_effect=fake_send_message):
                return await orchestrator.handle_event(office["id"], published)

        result = _run(scenario())
        assert result["status"] == "processed"
        decision = result["decision"]
        assert decision["action"] == "notify_advisor"
        assert decision["reasoning"] == "Explicação real gerada pelo modelo."
        assert decision["reasoning_source"] == "llm"
        assert decision["notification"]["status"] == "sent"
        assert sent["chat_id"] == "-100999"
        assert "Junqueira Capital" in sent["text"]
        assert len(fake_router.calls) == 1

    def test_llm_failure_degrades_to_honest_template_not_a_crash(self):
        async def scenario():
            office, client, event = await _office_with_client_and_violation()
            published = await AgentEventRepository().publish(office["id"], event)
            orchestrator = CoreOrchestrator(llm_router=_FailingLLMRouter())
            with patch("runtime.telegram.send_message", return_value={"ok": True}):
                return await orchestrator.handle_event(office["id"], published)

        result = _run(scenario())
        decision = result["decision"]
        assert decision["reasoning_source"] == "template_fallback"
        assert "Junqueira Capital" in decision["reasoning"]
        assert decision["notification"]["status"] == "sent"

    def test_no_llm_router_configured_uses_template_directly(self):
        async def scenario():
            office, client, event = await _office_with_client_and_violation()
            published = await AgentEventRepository().publish(office["id"], event)
            orchestrator = CoreOrchestrator(llm_router=None)
            with patch("runtime.telegram.send_message", return_value={"ok": True}):
                return await orchestrator.handle_event(office["id"], published)

        result = _run(scenario())
        assert result["decision"]["reasoning_source"] == "template_fallback"

    def test_reasoning_prompt_requests_allow_cloud(self):
        """Background agents must reach DeepSeek by default, unlike the
        interactive chat's local-first policy -- allow_cloud=True is how
        that's expressed on the request (see runtime/llm/policy.py)."""
        fake_router = _FakeLLMRouter()

        async def scenario():
            office, client, event = await _office_with_client_and_violation()
            published = await AgentEventRepository().publish(office["id"], event)
            orchestrator = CoreOrchestrator(llm_router=fake_router)
            with patch("runtime.telegram.send_message", return_value={"ok": True}):
                await orchestrator.handle_event(office["id"], published)

        _run(scenario())
        assert fake_router.calls[0].metadata["allow_cloud"] is True

    def test_no_telegram_chat_id_configured_is_honest_not_an_error(self):
        async def scenario():
            office, client, event = await _office_with_client_and_violation(telegram_chat_id=None)
            published = await AgentEventRepository().publish(office["id"], event)
            orchestrator = CoreOrchestrator(llm_router=_FakeLLMRouter())
            return await orchestrator.handle_event(office["id"], published)

        result = _run(scenario())
        assert result["decision"]["notification"]["status"] == "not_configured"

    def test_telegram_bot_token_not_configured_is_reported_honestly(self):
        from runtime.telegram import TelegramNotConfiguredError

        async def scenario():
            office, client, event = await _office_with_client_and_violation()
            published = await AgentEventRepository().publish(office["id"], event)
            orchestrator = CoreOrchestrator(llm_router=_FakeLLMRouter())
            with patch("runtime.telegram.send_message", side_effect=TelegramNotConfiguredError("no token")):
                return await orchestrator.handle_event(office["id"], published)

        result = _run(scenario())
        assert result["decision"]["notification"]["status"] == "not_configured"

    def test_telegram_send_error_is_reported_not_swallowed(self):
        from runtime.telegram import TelegramError

        async def scenario():
            office, client, event = await _office_with_client_and_violation()
            published = await AgentEventRepository().publish(office["id"], event)
            orchestrator = CoreOrchestrator(llm_router=_FakeLLMRouter())
            with patch("runtime.telegram.send_message", side_effect=TelegramError("boom")):
                return await orchestrator.handle_event(office["id"], published)

        result = _run(scenario())
        assert result["decision"]["notification"]["status"] == "error"
        assert "boom" in result["decision"]["notification"]["error"]

    def test_unknown_client_still_produces_a_decision_using_the_raw_id(self):
        """The client vanished (deleted?) between the observation cycle
        that published the event and the orchestrator handling it -- never
        crash, degrade to the id itself rather than fabricating a name."""
        async def scenario():
            tenant_repo = TenantRepository()
            office = await tenant_repo.create_office("Escritório Teste Ghost")
            await tenant_repo.set_telegram_chat_id(office["id"], "-100999")
            event = AgentEvent(
                type="PORTFOLIO_OUT_OF_PROFILE", source="compliance_agent",
                entity={"kind": "client", "id": "ghost-client"}, payload={"message": "x"}, priority="HIGH",
            )
            published = await AgentEventRepository().publish(office["id"], event)
            orchestrator = CoreOrchestrator(llm_router=None)
            with patch("runtime.telegram.send_message", return_value={"ok": True}):
                return await orchestrator.handle_event(office["id"], published)

        result = _run(scenario())
        assert "ghost-client" in result["decision"]["reasoning"]

    def test_decision_is_persisted_and_readable_back(self):
        async def scenario():
            office, client, event = await _office_with_client_and_violation()
            published = await AgentEventRepository().publish(office["id"], event)
            orchestrator = CoreOrchestrator(llm_router=_FakeLLMRouter())
            with patch("runtime.telegram.send_message", return_value={"ok": True}):
                await orchestrator.handle_event(office["id"], published)
            return await AgentEventRepository().get_event(office["id"], published["id"])

        stored = _run(scenario())
        assert stored["status"] == "processed"
        assert stored["decision"]["action"] == "notify_advisor"
