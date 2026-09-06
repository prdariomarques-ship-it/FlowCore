"""Specialized Autonomous Agents suite for FlowCore (Investment Copilot)."""

from __future__ import annotations

from typing import Any, Dict, Optional
from agents.base import BaseAgent
from runtime.tools.system_tools import register_system_tools
from runtime.tools.registry import get_tool_registry
from runtime.llm.model_router import get_model_router

# Ensure system tools are registered
register_system_tools()


class OpportunityAgent(BaseAgent):
    name = "opportunity_agent"
    description = "Detects investment and rebalancing opportunities from client deposits, cash drag, or asset maturities."
    version = "1.0.0"

    async def run(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        client_id = (context or {}).get("client_id", "cli_001")
        tool_reg = get_tool_registry()
        portfolio = tool_reg.execute("get_portfolio", {"client_id": client_id}, agent_id=self.name)
        router = get_model_router()

        prompt = (
            f"Analise o portfólio do cliente {client_id}: {portfolio}\n"
            "Identifique se há liquidez ociosa ou oportunidade de alocação de acordo com os limites definidos."
        )
        res = router.generate(prompt=prompt, agent_id=self.name)
        return {"status": "ok", "agent": self.name, "analysis": res.get("content")}


class ClientIntelligenceAgent(BaseAgent):
    name = "client_intelligence_agent"
    description = "Consolidates client profile, preferences, relationship timeline, and behavioral patterns."
    version = "1.0.0"

    async def run(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        client_id = (context or {}).get("client_id", "cli_001")
        tool_reg = get_tool_registry()
        client_info = tool_reg.execute("search_client", {"query": client_id}, agent_id=self.name)
        router = get_model_router()

        prompt = f"Gere um perfil consolidado de inteligência para o cliente: {client_info}"
        res = router.generate(prompt=prompt, agent_id=self.name)
        return {"status": "ok", "agent": self.name, "intelligence_brief": res.get("content")}


class MarketIntelligenceAgent(BaseAgent):
    name = "market_intelligence_agent"
    description = "Monitors macro/market events (Fed, Selic, IPCA, Ibovespa) and evaluates portfolio impact."
    version = "1.0.0"

    async def run(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        event_info = (context or {}).get("market_event", "Fed manteve taxa de juros elevada por mais tempo.")
        router = get_model_router()

        prompt = (
            f"Evento de Mercado: '{event_info}'\n"
            "Avalie o impacto potencial em carteiras de Renda Fixa e Renda Variável e recomende ajustes de proteção/oportunidade."
        )
        res = router.generate(prompt=prompt, agent_id=self.name)
        return {"status": "ok", "agent": self.name, "market_impact": res.get("content")}


class FollowUpAgent(BaseAgent):
    name = "follow_up_agent"
    description = "Identifies inactive clients or overdue tasks and drafts follow-up communication."
    version = "1.0.0"

    async def run(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        client_id = (context or {}).get("client_id", "cli_002")
        days_inactive = (context or {}).get("days_inactive", 74)
        tool_reg = get_tool_registry()

        draft = tool_reg.execute(
            "prepare_whatsapp_message",
            {
                "client_id": client_id,
                "message_text": f"Olá! Notei que não nos falamos há {days_inactive} dias. Gostaria de revisar sua carteira frente ao cenário atual?",
                "context": "Follow-up de inatividade",
            },
            agent_id=self.name,
        )

        return {"status": "ok", "agent": self.name, "follow_up_draft": draft}


class CommunicationAgent(BaseAgent):
    name = "communication_agent"
    description = "Prepares and dispatches internal or external client communications subject to approval rules."
    version = "1.0.0"

    async def run(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        message = (context or {}).get("message", "Aviso de rebalanceamento recomendado.")
        recipient = (context or {}).get("recipient", "advisor")
        tool_reg = get_tool_registry()

        res = tool_reg.execute("send_telegram", {"message": message, "recipient": recipient}, agent_id=self.name)
        return {"status": "ok", "agent": self.name, "dispatch": res}
