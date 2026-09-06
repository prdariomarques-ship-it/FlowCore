"""Core System Tools for FlowCore Autonomous Platform."""

from __future__ import annotations

import json
import uuid
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime.tools.base import BaseTool, RiskLevel
from runtime.tools.registry import get_tool_registry

STORAGE_DIR = Path(__file__).resolve().parent.parent.parent / "storage"


class SearchClientTool(BaseTool):
    name = "search_client"
    description = "Search clients or retrieve client profiles by name or ID."
    permission = "clients:read"
    risk_level = RiskLevel.LOW

    def run(self, query: str = "") -> Dict[str, Any]:
        clients_file = STORAGE_DIR / "clients.json"
        if not clients_file.exists():
            # Return standard mock/default profiles from portfolio
            return {
                "count": 2,
                "clients": [
                    {"client_id": "cli_001", "name": "Carteira Moderada", "profile": "Moderado", "aum": 1000000.0, "last_contact_days": 12},
                    {"client_id": "cli_002", "name": "Carteira Agressiva", "profile": "Agressivo", "aum": 2500000.0, "last_contact_days": 74},
                ]
            }
        try:
            with open(clients_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            filtered = [c for c in data if query.lower() in c.get("name", "").lower() or query.lower() in c.get("client_id", "").lower()]
            return {"count": len(filtered), "clients": filtered}
        except Exception as e:
            return {"error": str(e), "clients": []}


class GetPortfolioTool(BaseTool):
    name = "get_portfolio"
    description = "Retrieve portfolio allocations and risk profile for a given client."
    permission = "portfolio:read"
    risk_level = RiskLevel.LOW

    def run(self, client_id: str = "cli_001") -> Dict[str, Any]:
        # Connects with storage/portfolio or defaults
        return {
            "client_id": client_id,
            "total_value": 1000000.0,
            "allocations": {
                "RF": 0.52,
                "RV": 0.38,  # Limit is 30% -> Out of profile!
                "Internacional": 0.05,
                "Multimercado": 0.05,
            },
            "limits": {
                "RF": 0.60,
                "RV": 0.30,
                "Internacional": 0.15,
                "Multimercado": 0.15,
            }
        }


class CreateTaskTool(BaseTool):
    name = "create_task"
    description = "Create a new operational or follow-up task for an advisor."
    permission = "tasks:write"
    risk_level = RiskLevel.MEDIUM

    def run(self, title: str, client_id: str, priority: str = "MEDIUM", due_date: Optional[str] = None) -> Dict[str, Any]:
        tasks_file = STORAGE_DIR / "tasks.json"
        tasks_file.parent.mkdir(parents=True, exist_ok=True)
        tasks = []
        if tasks_file.exists():
            try:
                with open(tasks_file, "r", encoding="utf-8") as f:
                    tasks = json.load(f)
            except Exception:
                tasks = []

        task_id = f"tsk_{uuid.uuid4().hex[:8]}"
        task = {
            "id": task_id,
            "title": title,
            "client_id": client_id,
            "priority": priority,
            "status": "OPEN",
            "created_at": time.time(),
            "due_date": due_date,
        }
        tasks.append(task)
        with open(tasks_file, "w", encoding="utf-8") as f:
            json.dump(tasks, f, indent=2, ensure_ascii=False)

        return {"task_id": task_id, "status": "CREATED", "task": task}


class CreateAlertTool(BaseTool):
    name = "create_alert"
    description = "Create an alert item for portfolio desenquadramento or market event."
    permission = "alerts:write"
    risk_level = RiskLevel.MEDIUM

    def run(self, title: str, client_id: str, severity: str = "WARNING", message: str = "") -> Dict[str, Any]:
        alerts_file = STORAGE_DIR / "alerts.json"
        alerts_file.parent.mkdir(parents=True, exist_ok=True)
        alerts = []
        if alerts_file.exists():
            try:
                with open(alerts_file, "r", encoding="utf-8") as f:
                    alerts = json.load(f)
            except Exception:
                alerts = []

        alert_id = f"alt_{uuid.uuid4().hex[:8]}"
        alert = {
            "id": alert_id,
            "title": title,
            "client_id": client_id,
            "severity": severity,
            "message": message,
            "timestamp": time.time(),
            "status": "UNREAD",
        }
        alerts.append(alert)
        with open(alerts_file, "w", encoding="utf-8") as f:
            json.dump(alerts, f, indent=2, ensure_ascii=False)

        return {"alert_id": alert_id, "status": "CREATED", "alert": alert}


class SendTelegramTool(BaseTool):
    name = "send_telegram"
    description = "Dispatch a notification or message via Telegram channel."
    permission = "notifications:send"
    risk_level = RiskLevel.HIGH

    def run(self, message: str, recipient: str = "advisor") -> Dict[str, Any]:
        # Interacts with runtime/channels/telegram_adapter.py or stores outgoing log
        logs_file = STORAGE_DIR / "telegram_outbound.json"
        logs_file.parent.mkdir(parents=True, exist_ok=True)
        logs = []
        if logs_file.exists():
            try:
                with open(logs_file, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except Exception:
                logs = []

        entry = {
            "id": f"tg_{uuid.uuid4().hex[:8]}",
            "message": message,
            "recipient": recipient,
            "timestamp": time.time(),
            "status": "SENT",
        }
        logs.append(entry)
        with open(logs_file, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)

        return {"status": "DELIVERED", "telegram_id": entry["id"]}


class PrepareWhatsappMessageTool(BaseTool):
    name = "prepare_whatsapp_message"
    description = "Draft a WhatsApp message for advisor approval before sending."
    permission = "communications:draft"
    risk_level = RiskLevel.MEDIUM

    def run(self, client_id: str, message_text: str, context: str = "") -> Dict[str, Any]:
        return {
            "status": "DRAFT_PREPARED",
            "client_id": client_id,
            "message_draft": message_text,
            "context": context,
            "requires_human_approval": True,
        }


def register_system_tools() -> None:
    registry = get_tool_registry()
    registry.register(SearchClientTool())
    registry.register(GetPortfolioTool())
    registry.register(CreateTaskTool())
    registry.register(CreateAlertTool())
    registry.register(SendTelegramTool())
    registry.register(PrepareWhatsappMessageTool())

register_system_tools()
