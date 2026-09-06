"""FlowCore — client review-request outreach (email + WhatsApp).

Turns a real ComplianceAgent violation into a drafted, human-reviewable
invitation to a portfolio review meeting — and, once an advisor
explicitly approves it, sends it through the already-existing transports
(runtime/email_sender.py, runtime/whatsapp.py).

Deliberately NOT automatic. Per the Wealth Copilot spec's three-tier
automation rule (agents/*.py's shared "OBSERVAR -> ANALISAR -> EXPLICAR
-> PRIORIZAR -> SUGERIR" principle, and the explicit "never send
messages automatically without authorization when there is financial,
legal, or relationship risk"), contacting a real client is a
relationship-risk action — this module only ever drafts and sends on an
explicit per-client call from a route the advisor triggers (see
api/dashboard_routes.py's POST /api/clients/{id}/request-review); there
is no scheduler anywhere that calls send_review_request() on its own.

Drafts are template-based, not LLM-generated: every sentence traces to a
real field (client name, the violation's own message, advisor/office
name) — nothing invented, matching the same "every recommendation must
be explainable" rule IntelligenceEngine already follows.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_DATA_DIR = Path.home() / ".flowcore"


def draft_review_request(client_name: str, violations: list[dict[str, Any]], advisor_name: str, office_name: str) -> dict[str, str]:
    """Pure function: real inputs in, a drafted subject/body/whatsapp text
    out. No I/O, no side effects — safe to call just to preview a draft
    before anyone decides to send it."""
    reasons = [v["message"] for v in violations]
    reasons_bullets = "\n".join(f"- {r}" for r in reasons)
    severity = "CRÍTICA" if any(v["severity"] == "CRITICAL" for v in violations) else "de atenção"

    subject = f"{client_name}, vamos revisar sua carteira?"
    body = (
        f"Olá, {client_name}!\n\n"
        f"Ao revisar sua carteira, identificamos {len(violations)} ponto(s) fora da política de "
        f"alocação combinada (classificação {severity}):\n\n"
        f"{reasons_bullets}\n\n"
        "Gostaríamos de agendar uma breve conversa para revisar juntos esses pontos e "
        "confirmar se ainda fazem sentido para o seu momento atual.\n\n"
        "Pode nos indicar um horário nos próximos dias?\n\n"
        f"Atenciosamente,\n{advisor_name}\n{office_name}"
    )
    whatsapp_text = (
        f"Olá {client_name}! Aqui é {advisor_name}, da {office_name}. "
        f"Identificamos {len(violations)} ponto(s) na sua carteira fora da política combinada "
        f"(ex: {reasons[0]}). Podemos agendar uma breve revisão? Fico à disposição."
    )
    return {"subject": subject, "body": body, "whatsapp_text": whatsapp_text}


def _audit_path(office_id: str) -> Path:
    return _DATA_DIR / f"outreach_audit_{office_id}.jsonl"


def _record_audit(office_id: str, entry: dict[str, Any]) -> None:
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        with _audit_path(office_id).open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass  # audit logging must never break the send attempt itself


def send_review_request(
    office_id: str, client: dict[str, Any], draft: dict[str, str], channels: list[str], triggered_by_user_id: str,
) -> dict[str, Any]:
    """Attempts to send `draft` to `client` over each requested channel.

    Every channel result is one of: "sent", "no_contact_info" (the
    client has no email/phone on file — never invented), "not_configured"
    (the transport itself isn't set up), or "error" (with the real
    exception message). Every attempt — success or failure — is appended
    to this office's own outreach audit log, never a shared one.
    """
    results: dict[str, dict[str, Any]] = {}

    if "email" in channels:
        results["email"] = _send_email_channel(client, draft)
    if "whatsapp" in channels:
        results["whatsapp"] = _send_whatsapp_channel(client, draft)

    _record_audit(office_id, {
        "timestamp": time.time(), "client_id": client["id"], "client_name": client["name"],
        "channels": channels, "results": results, "triggered_by_user_id": triggered_by_user_id,
    })
    return results


def _send_email_channel(client: dict[str, Any], draft: dict[str, str]) -> dict[str, Any]:
    from runtime.email_sender import EmailError, EmailNotConfiguredError, is_configured, send_email

    if not client.get("email"):
        return {"status": "no_contact_info"}
    if not is_configured():
        return {"status": "not_configured"}
    try:
        send_email(client["email"], draft["subject"], draft["body"])
        return {"status": "sent", "to": client["email"]}
    except EmailNotConfiguredError:
        return {"status": "not_configured"}
    except EmailError as e:
        return {"status": "error", "error": str(e)}


def _send_whatsapp_channel(client: dict[str, Any], draft: dict[str, str]) -> dict[str, Any]:
    from runtime.whatsapp import WhatsAppError, WhatsAppNotConfiguredError, send_message

    if not client.get("phone"):
        return {"status": "no_contact_info"}
    try:
        send_message(client["phone"], draft["whatsapp_text"])
        return {"status": "sent", "to": client["phone"]}
    except WhatsAppNotConfiguredError:
        return {"status": "not_configured"}
    except WhatsAppError as e:
        return {"status": "error", "error": str(e)}
