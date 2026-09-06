"""ComplianceAgent — Analyzes portfolio positions vs allocation limits and flags violations."""

from __future__ import annotations

from typing import Any
from agents.base import BaseAgent


# Default client portfolios for FlowCore compliance monitoring
DEFAULT_SAMPLE_CLIENTS = [
    {
        "client_id": "cli_001",
        "client_name": "Junqueira Capital",
        "allocations": {"renda_variavel": 67.0},
        "limits": {"renda_variavel": 65.0},
    },
    {
        "client_id": "cli_002",
        "client_name": "Kessler Family Office",
        "allocations": {"renda_fixa": 11.5},
        "limits": {"renda_fixa": 10.0},
    },
    {
        "client_id": "cli_003",
        "client_name": "Leitão Wealth",
        "allocations": {"internacional": 8.0},
        "limits": {"internacional": 7.0},
    },
    {
        "client_id": "cli_004",
        "client_name": "Nogueira Family Office",
        "allocations": {"renda_variavel": 68.0},
        "limits": {"renda_variavel": 55.0},
    },
    {
        "client_id": "cli_005",
        "client_name": "Oliveira Patrimonial",
        "allocations": {"renda_variavel": 17.0},
        "limits": {"renda_variavel": 10.0},
    },
    {
        "client_id": "cli_006",
        "client_name": "Pimentel Capital",
        "allocations": {"renda_variavel": 72.0},
        "limits": {"renda_variavel": 65.0},
    },
]

CLASS_LABEL_MAP = {
    "renda_variavel": "Excesso de Renda Variável",
    "renda_fixa": "Excesso de Renda Fixa",
    "internacional": "Excesso de Renda Fixa/Ativos Internacional",
    "multimercado": "Excesso em Multimercado",
    "alternativos": "Excesso em Alternativos",
}


class ComplianceAgent(BaseAgent):
    """Monitors investment portfolios and identifies allocation desenquadramentos."""

    name: str = "compliance_agent"
    description: str = "Analisa posições de carteiras e identifica violações de regras de alocação."
    version: str = "0.1.0"

    def analyze_portfolio(self, client: dict[str, Any]) -> list[dict[str, Any]]:
        """Analyze a single client portfolio for compliance violations."""
        violations = []
        client_id = client.get("client_id", "unknown")
        client_name = client.get("client_name", "Cliente")

        allocations = client.get("allocations", {})
        limits = client.get("limits", {})

        for cls_name, current_val in allocations.items():
            limit_val = limits.get(cls_name)
            if limit_val is None:
                continue

            if current_val > limit_val:
                diff = round(current_val - limit_val, 2)
                # Severity rule: > limit + 5 p.p. -> CRITICAL (🔴), else WARNING (🟡)
                if diff > 5.0:
                    severity = "CRITICAL"
                    status_emoji = "🔴"
                    suggested_action = f"Realizar rebalanceamento urgente de {cls_name.replace('_', ' ')}: reduzir {diff} p.p."
                else:
                    severity = "WARNING"
                    status_emoji = "🟡"
                    suggested_action = f"Acompanhar exposição a {cls_name.replace('_', ' ')}: excesso de {diff} p.p."

                violation_type = CLASS_LABEL_MAP.get(
                    cls_name, f"Excesso de {cls_name.replace('_', ' ').title()}"
                )

                violations.append({
                    "client_id": client_id,
                    "client_name": client_name,
                    "asset_class": cls_name,
                    "type": violation_type,
                    "current": round(current_val, 2),
                    "limit": round(limit_val, 2),
                    "diff": diff,
                    "severity": severity,
                    "status_emoji": status_emoji,
                    "message": f"{violation_type}: {current_val}% vs limite de {limit_val}% ({diff:+g} p.p.)",
                    "suggested_action": suggested_action,
                })

        return violations

    async def run(self, context: dict | None = None) -> dict[str, Any]:
        """Run compliance check over single client or multiple clients in context."""
        context = context or {}
        clients = []

        if "client" in context:
            clients.append(context["client"])
        elif "clients" in context and isinstance(context["clients"], list):
            clients = context["clients"]
        else:
            clients = DEFAULT_SAMPLE_CLIENTS

        all_violations = []
        for client in clients:
            violations = self.analyze_portfolio(client)
            all_violations.extend(violations)

        critical_count = sum(1 for v in all_violations if v["severity"] == "CRITICAL")
        warning_count = sum(1 for v in all_violations if v["severity"] == "WARNING")

        return {
            "status": "ok",
            "total": len(all_violations),
            "critical": critical_count,
            "warnings": warning_count,
            "items": all_violations,
        }
