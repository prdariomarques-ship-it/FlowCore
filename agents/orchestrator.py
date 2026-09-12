"""FlowCore CoreOrchestrator -- the classify -> gather context -> reason
-> decide -> execute -> record loop every autonomous-agent event goes
through (Agent Runtime architecture, §6).

Two event types handled so far, each fixed at its own autonomy level
(§8) rather than letting the model pick:

  PORTFOLIO_OUT_OF_PROFILE   LEVEL 2 -- notifies the office's OWN advisor
                             via Telegram. No approval needed: telling an
                             advisor "look at this" carries no financial/
                             legal/relationship risk.
  PORTFOLIO_BACK_IN_PROFILE  LEVEL 2 -- same reasoning, good news instead
                             of bad; also marks the original violation
                             event resolved (see agents/observer_loop.py).
  CLIENT_FOLLOWUP_OVERDUE    LEVEL 3 -- an unaddressed violation that's
                             been open too long with no outreach attempt.
                             This one NEVER contacts the client directly:
                             it drafts the message (reusing
                             runtime/client_outreach.draft_review_request)
                             and files it in AgentApprovalRepository as
                             "pending", then notifies the advisor that an
                             approval is waiting. The actual send only
                             happens once a human calls
                             AgentApprovalRepository.decide("approved",
                             ...) from the dashboard -- see
                             api/dashboard_routes.py's
                             POST /api/agent-approvals/{id}/approve. This
                             orchestrator does not, and must not, cross
                             that line on its own.

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
import json
from pathlib import Path
from typing import Any, Awaitable, Callable

_DATA_DIR = Path.home() / ".flowcore"


def _advisor_name_for_office(office_id: str) -> str:
    """Best-effort real name from the office's own advisor card (same
    file api/dashboard_routes.py's /api/advisor reads/writes) -- "Equipe"
    when none is configured, never a guessed or hardcoded person's name."""
    path = _DATA_DIR / f"advisor_{office_id}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        name = data.get("name")
        if name:
            return name
    except (OSError, json.JSONDecodeError):
        pass
    return "Equipe"


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

    # ── PORTFOLIO_OUT_OF_PROFILE (LEVEL 2: notify only) ──────────────────────

    async def _handle_portfolio_out_of_profile(self, office_id: str, event: dict[str, Any]) -> dict[str, Any]:
        from storage.client_repo import ClientRepository
        from storage.tenant_repo import TenantRepository

        client_id = event["entity"].get("id", "")
        client = await ClientRepository().get_client(office_id, client_id)
        office = await TenantRepository().get_office(office_id)

        reasoning, reasoning_source = await self._reason_violation(client, event, office, office_id)
        emoji = "🔴" if event.get("priority") in ("CRITICAL", "HIGH") else "🟡"
        client_name = client["name"] if client else client_id
        notification = await self._send_telegram(office, f"{emoji} {client_name}\n\n{reasoning}")

        decision = {
            "agent": "client_intelligence", "action": "notify_advisor",
            "reasoning": reasoning, "reasoning_source": reasoning_source, "notification": notification,
        }
        return await self._record(office_id, event, "processed", decision)

    # ── PORTFOLIO_BACK_IN_PROFILE (LEVEL 2: good news, notify only) ─────────

    async def _handle_portfolio_back_in_profile(self, office_id: str, event: dict[str, Any]) -> dict[str, Any]:
        from storage.client_repo import ClientRepository

        client_id = event["entity"].get("id", "")
        client = await ClientRepository().get_client(office_id, client_id)
        client_name = client["name"] if client else client_id

        office = await self._get_office(office_id)
        notification = await self._send_telegram(
            office, f"🟢 {client_name} voltou a ficar dentro da política de alocação combinada.",
        )
        decision = {"agent": "client_intelligence", "action": "notify_advisor_recovered", "notification": notification}
        return await self._record(office_id, event, "processed", decision)

    # ── CLIENT_FOLLOWUP_OVERDUE (LEVEL 3: propose, never send alone) ────────

    async def _handle_client_followup_overdue(self, office_id: str, event: dict[str, Any]) -> dict[str, Any]:
        from runtime.client_outreach import draft_review_request
        from storage.agent_approval_repo import AgentApprovalRepository
        from storage.client_repo import ClientRepository

        client_id = event["entity"].get("id", "")
        client = await ClientRepository().get_client(office_id, client_id)
        if client is None:
            return await self._ignore(office_id, event, f"client {client_id!r} not found")

        approval_repo = AgentApprovalRepository()
        already_pending = [
            a for a in await approval_repo.list_approvals(office_id, status="pending")
            if a["action_type"] == "contact_client" and a["entity"].get("id") == client_id
        ]
        if already_pending:
            # Don't stack a second pending approval (or send a second
            # "please approve" ping) for the same client while one is
            # already waiting on a human -- re-asking every observation
            # cycle would make the queue worth ignoring.
            decision = {"agent": "followup_agent", "action": "already_pending", "approval_id": already_pending[0]["id"]}
            return await self._record(office_id, event, "processed", decision)

        office = await self._get_office(office_id)
        violations = event["payload"].get("violations", [])
        advisor_name = _advisor_name_for_office(office_id)
        office_name = office["name"] if office else ""
        draft = draft_review_request(client["name"], violations, advisor_name, office_name)

        approval = await approval_repo.create(
            office_id, event["id"], "followup_agent", "contact_client", event["entity"],
            {"client_id": client_id, "client_name": client["name"], "draft": draft, "channels": ["email", "whatsapp"]},
        )

        reasoning, reasoning_source = await self._reason_followup(client, event, office, office_id)
        notification = await self._send_telegram(
            office,
            f"🟠 {client['name']} precisa de aprovação\n\n{reasoning}\n\n"
            f"Rascunho pronto -- aprove em /api/agent-approvals/{approval['id']}/approve.",
        )

        decision = {
            "agent": "followup_agent", "action": "propose_client_contact", "approval_id": approval["id"],
            "reasoning": reasoning, "reasoning_source": reasoning_source, "notification": notification,
        }
        return await self._record(office_id, event, "processed", decision)

    # ── Reasoning ────────────────────────────────────────────────────────────

    async def _reason_violation(
        self, client: dict[str, Any] | None, event: dict[str, Any], office: dict[str, Any] | None,
        office_id: str,
    ) -> tuple[str, str]:
        message = event["payload"].get("message", "")
        client_name = client["name"] if client else event["entity"].get("id", "cliente")
        office_name = office["name"] if office else ""
        prompt = (
            f"Cliente {client_name}, do escritório {office_name}, está com a carteira fora da política de "
            f"alocação combinada: {message}\n\n"
            "Em no máximo duas frases, explique objetivamente o que isso significa e recomende o próximo "
            "passo para o advisor. Baseie-se só nesse fato -- não invente números ou histórico que não "
            "foram informados."
        )
        fallback = f"{client_name}: {message} Recomenda-se revisar a carteira com o cliente e avaliar reequilíbrio."
        return await self._call_llm(prompt, fallback, office_id)

    async def _reason_followup(
        self, client: dict[str, Any], event: dict[str, Any], office: dict[str, Any] | None,
        office_id: str,
    ) -> tuple[str, str]:
        days_open = event["payload"].get("days_open")
        days_text = f"há {days_open} dia(s)" if days_open is not None else "há um tempo"
        prompt = (
            f"O cliente {client['name']} está com uma violação de alocação em aberto {days_text}, sem "
            "nenhuma tentativa de contato registrada. Em no máximo duas frases, explique por que isso "
            "merece atenção agora e o que o advisor deve decidir. Baseie-se só nesses fatos -- não invente "
            "detalhes do relacionamento com o cliente que não foram informados."
        )
        fallback = (
            f"{client['name']} está com uma violação em aberto {days_text} sem contato registrado. "
            "Rascunho de mensagem de revisão pronto para aprovação."
        )
        return await self._call_llm(prompt, fallback, office_id)

    async def _call_llm(self, prompt: str, fallback: str, office_id: str) -> tuple[str, str]:
        if self._llm_router is not None:
            try:
                from runtime.llm import LLMRequest

                request = LLMRequest(
                    prompt=prompt,
                    metadata={"allow_cloud": True, "purpose": "orchestrator_reasoning", "office_id": office_id},
                )
                response = await asyncio.to_thread(self._llm_router.generate, request)
                text = response.text.strip()
                if text:
                    return text, "llm"
            except Exception:
                pass  # fall through to the deterministic template below
        return fallback, "template_fallback"

    # ── Telegram ─────────────────────────────────────────────────────────────

    async def _get_office(self, office_id: str) -> dict[str, Any] | None:
        from storage.tenant_repo import TenantRepository

        return await TenantRepository().get_office(office_id)

    async def _send_telegram(self, office: dict[str, Any] | None, text: str) -> dict[str, Any]:
        chat_id = office.get("telegram_chat_id") if office else None
        if not chat_id:
            return {"status": "not_configured"}
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
        "PORTFOLIO_BACK_IN_PROFILE": _handle_portfolio_back_in_profile,
        "CLIENT_FOLLOWUP_OVERDUE": _handle_client_followup_overdue,
    }
