"""FlowCore Rebalancing Agent.
Prepares actionable rebalancing proposals for non-compliant portfolios, calculating asset class shifts,
financial amounts, liquidity impact, and risk adjustment details.
"""

from typing import Any, Dict, List, Optional
from agents.base import BaseAgent


class RebalancingAgent(BaseAgent):
    """Agent that generates actionable rebalancing proposals."""

    name = "RebalancingAgent"
    description = "Generates target rebalancing trades and risk adjustments."
    version = "0.2.0"

    async def run(self, input_data: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Generates rebalancing proposals based on portfolio violations."""
        input_data = input_data or {}
        portfolio = input_data.get("portfolio", {})
        violations = input_data.get("violations", [])
        total_value = portfolio.get("total_value", sum(item.get("value", 0.0) for item in portfolio.get("holdings", [])))

        if not violations or total_value <= 0:
            return {
                "proposed": False,
                "message": "Nenhum rebalanceamento necessário.",
                "trades": [],
            }

        trades = []

        for v in violations:
            asset_class = v.get("asset_class", "Renda Variável")
            diff_pp = v.get("diff_pp", 0.0)
            reduce_value = round((diff_pp / 100.0) * total_value, 2)

            trades.append({
                "action": "SELL",
                "asset_class": asset_class,
                "percentage_delta": -diff_pp,
                "approximate_value": reduce_value,
                "reason": f"Reduzir excesso de {diff_pp} p.p. acima do teto de compliance.",
                "liquidity_impact": "Alta (Ativos negociados em mercado secundário)",
                "risk_impact": "Redução do VaR e volatilidade da carteira",
            })

            trades.append({
                "action": "BUY",
                "asset_class": "Renda Fixa / Tesouro Selic",
                "percentage_delta": diff_pp,
                "approximate_value": reduce_value,
                "reason": f"Alocar recursos reduzidos de {asset_class} para enquadrar perfil.",
                "liquidity_impact": "Liquidez D+0 / D+1",
                "risk_impact": "Preservação de capital com rendimento CDI",
            })

        proposal = {
            "proposed": True,
            "client_id": portfolio.get("client_id", input_data.get("client_id")),
            "client_name": portfolio.get("client_name", input_data.get("client_name")),
            "portfolio_value": total_value,
            "trades_count": len(trades),
            "trades": trades,
            "summary": f"Proposta de rebalanceamento gerada: {len(trades)} operações sugeridas para enquadramento.",
        }

        return proposal
