"""Telegram Channel Adapter for proactive notifications and natural language queries."""

from __future__ import annotations

import json
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime.events.schemas import Event, EventPriority
from runtime.events.bus import get_event_bus
from runtime.llm.model_router import get_model_router
from runtime.approval.manager import get_approval_manager

STORAGE_DIR = Path(__file__).resolve().parent.parent.parent / "storage"


class TelegramAdapter:
    """Channel adapter for Telegram notifications and commands."""

    def __init__(self) -> None:
        self.router = get_model_router()
        self.bus = get_event_bus()

    def handle_natural_language_query(self, user_query: str) -> str:
        """Handle incoming query e.g. 'Quem precisa da minha atenção hoje?'."""
        approval_mgr = get_approval_manager()
        pending_approvals = approval_mgr.list_pending_approvals()

        prompt = (
            f"Pergunta do Advisor via Telegram: '{user_query}'\n"
            f"Aprovações pendentes no sistema: {len(pending_approvals)}\n"
            "Responda de forma concisa, direta e priorizada em português (Investment Copilot)."
        )

        res = self.router.generate(prompt=prompt, agent_id="telegram_adapter")
        return res.get("content", "Sem informações no momento.")

    def notify_proactive_alert(self, event: Event) -> Dict[str, Any]:
        """Dispatch a proactive alert message for high priority events."""
        msg = f"🚨 *ALERTA PROATIVO FlowCore*\nTipo: {event.type}\nCliente: {event.entity}\nPrioridade: {event.priority.value}\nDetalhes: {event.payload}"

        outbound_file = STORAGE_DIR / "telegram_outbound.json"
        outbound_file.parent.mkdir(parents=True, exist_ok=True)
        logs = []
        if outbound_file.exists():
            try:
                with open(outbound_file, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except Exception:
                logs = []

        entry = {
            "event_id": event.id,
            "message": msg,
            "status": "DELIVERED",
        }
        logs.append(entry)
        with open(outbound_file, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)

        return entry


_telegram_adapter_instance = TelegramAdapter()

def get_telegram_adapter() -> TelegramAdapter:
    return _telegram_adapter_instance
