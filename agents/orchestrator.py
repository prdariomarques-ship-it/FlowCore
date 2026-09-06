"""FlowCore CoreOrchestrator -- the classify -> gather context -> reason
-> decide -> execute -> record loop every autonomous-agent event goes
through (Agent Runtime architecture, §6).

Deliberately narrow for this first real, end-to-end slice: one event
type handled (PORTFOLIO_OUT_OF_PROFILE), one action available
(notify_advisor via Telegram), fixed at autonomy LEVEL 2 (§8 -- "pode
criar tarefas, alertas e relatórios"). No human approval is required for
this action because it notifies the office's OWN advisor, not a client
or any third party -- there is no financial/legal/relationship risk in
telling an advisor "look at this." Contacting a real client stays at
LEVEL 3+ and already requires an explicit human click (see
runtime/client_outreach.py's module docstring) -- this orchestrator does
not, and must not, cross that line on its own.

An event type with no registered handler is never silently dropped or
guessed at: it is recorded with status="ignored" and an honest reason,
per this project's "never simulate intelligence" rule -- a missing
capability must look like a missing capability, not like nothing
happened.

Reasoning calls the LLM Router with allow_cloud=True -- per the 2026-09
decision that autonomous background agents (unlike the interactive
local-first chat) reach DeepSeek by default. If no cloud provider is
configured, or the call fails for any reason, this degrades to a
deterministic templated explanation built only from the event's own real
fields -- never fabricated -- and the record always says which path
produced it (reasoning_source: "llm" | "template_fallback"), so nothing
degraded is ever presented as if a model reasoned about it.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable


class CoreOrchestrator:
    def __init__(self, llm_router: Any | None = None) -> None:
        # Injected, not imported from service.py -- lets tests pass a
        # fake router, matching runtime/agent/engine.py's AgentEngine's
        # own constructor convention.
        self._llm_router = llm_router

    async def handle_event(self, office_id: str, event: dict[str, Any]) -> dict[str, Any]:
        handler = self._HANDLERS.get(event["type"])
        if handler is None:
            return await self._ignore(office_id, event, f"no handler registered for event type {event['type']!r}")
        return await handler(self, office_id, event)

    # ── PORTFOLIO_OUT_OF_PROFILE ─────────────────────────────────────────────

    async def _handle_portfolio_out_of_profile(self, office_id: str, event: dict[str, Any]) -> dict[str, Any]:
        from storage.client_repo import ClientRepository
        from storage.tenant_repo import TenantRepository

        client_id = event["entity"].get("id", "")
        client = await ClientRepository().get_client(office_id, client_id)
        office = await TenantRepository().get_office(office_id)

        reasoning, reasoning_source = await self._reason(client, event, office)
        notification = await self._notify_advisor(office, client, event, reasoning)

        decision = {
            "agent": "client_intelligence",
            "action": "notify_advisor",
            "reasoning": reasoning,
            "reasoning_source": reasoning_source,
            "notification": notification,
        }
        return await self._record(office_id, event, "processed", decision)

    async def _reason(
        self, client: dict[str, Any] | None, event: dict[str, Any], office: dict[str, Any] | None,
    ) -> tuple[str, str]:
        message = event["payload"].get("message", "")
        client_name = client["name"] if client else event["entity"].get("id", "cliente")
        office_name = office["name"] if office else ""

        if self._llm_router is not None:
            try:
                from runtime.llm import LLMRequest

                prompt = (
                    f"Cliente {client_name}, do escritório {office_name}, está com a carteira fora da "
                    f"política de alocação combinada: {message}\n\n"
                    "Em no máximo duas frases, explique objetivamente o que isso significa e recomende o "
                    "próximo passo para o advisor. Baseie-se só nesse fato -- não invente números ou "
                    "histórico que não foram informados."
                )
                request = LLMRequest(prompt=prompt, metadata={"allow_cloud": True, "purpose": "orchestrator_reasoning"})
                response = await asyncio.to_thread(self._llm_router.generate, request)
                text = response.text.strip()
                if text:
                    return text, "llm"
            except Exception:
                pass  # fall through to the deterministic template below

        return (
            f"{client_name}: {message} Recomenda-se revisar a carteira com o cliente e avaliar reequilíbrio.",
            "template_fallback",
        )

    async def _notify_advisor(
        self, office: dict[str, Any] | None, client: dict[str, Any] | None,
        event: dict[str, Any], reasoning: str,
    ) -> dict[str, Any]:
        chat_id = office.get("telegram_chat_id") if office else None
        if not chat_id:
            return {"status": "not_configured"}

        client_name = client["name"] if client else event["entity"].get("id", "cliente")
        severity_emoji = "🔴" if event.get("priority") in ("CRITICAL", "HIGH") else "🟡"
        text = f"{severity_emoji} {client_name}\n\n{reasoning}"
        try:
            from runtime.telegram import TelegramError, TelegramNotConfiguredError, send_message

            await asyncio.to_thread(send_message, text, chat_id)
            return {"status": "sent", "chat_id": chat_id}
        except TelegramNotConfiguredError:
            # The office registered a destination chat, but this FlowCore
            # install has no TELEGRAM_BOT_TOKEN of its own -- honestly
            # distinct from a real send failure (TelegramError below).
            return {"status": "not_configured"}
        except TelegramError as e:
            return {"status": "error", "error": str(e)}

    # ── Fallback / bookkeeping ───────────────────────────────────────────────

    async def _ignore(self, office_id: str, event: dict[str, Any], reason: str) -> dict[str, Any]:
        return await self._record(office_id, event, "ignored", {"reason": reason})

    async def _record(self, office_id: str, event: dict[str, Any], status: str, decision: dict[str, Any]) -> dict[str, Any]:
        from storage.agent_event_repo import AgentEventRepository

        return await AgentEventRepository().record_decision(office_id, event["id"], status, decision)

    _HANDLERS: dict[str, Callable[["CoreOrchestrator", str, dict[str, Any]], Awaitable[dict[str, Any]]]] = {
        "PORTFOLIO_OUT_OF_PROFILE": _handle_portfolio_out_of_profile,
    }
