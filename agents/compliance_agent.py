"""FlowCore Compliance Agent — Wealth Copilot allocation & rule compliance monitor.

Analyzes investment portfolios against defined allocation rules and sleeve limits.
Classifies status into:
  🟢 NORMAL (OK)
  🟡 ATENÇÃO (WARNING)
  🔴 DESENQUADRADO (CRITICAL)

Produces structured violation alerts for display in Web UI, APIs, and AI chat.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.base import BaseAgent
from loguru import logger

_DATA_DIR = Path.home() / ".flowcore"
_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


class ComplianceAgent(BaseAgent):
    name = "compliance"
    description = "Analisa carteiras e detecta desenquadramentos em relação aos limites estipulados."
    version = "0.1.0"

    async def run(self, context: dict | None = None) -> dict[str, Any]:
        """Execute compliance checks on provided or stored portfolios.

        Returns:
            dict with keys:
              - status: "ok"
              - data: {
                  "total": int,
                  "critical": int,
                  "warnings": int,
                  "items": list[dict]
                }
        """
        ctx = context or {}
        portfolios = self._load_portfolios(ctx)

        all_items: list[dict[str, Any]] = []
        critical_count = 0
        warning_count = 0

        for pf in portfolios:
            violations = self.evaluate_portfolio(pf)
            for v in violations:
                all_items.append(v)
                if v.get("severity") == "CRITICAL":
                    critical_count += 1
                elif v.get("severity") == "WARNING":
                    warning_count += 1

        total_count = len(all_items)

        result_data = {
            "total": total_count,
            "critical": critical_count,
            "warnings": warning_count,
            "items": all_items,
        }

        logger.info(
            "Compliance check completed: {} violations ({} critical, {} warnings)",
            total_count,
            critical_count,
            warning_count,
        )

        return {
            "status": "ok",
            "data": result_data,
        }

    def _load_portfolios(self, context: dict) -> list[dict[str, Any]]:
        """Load portfolios from context, ~/.flowcore/portfolios.json, or bundled config."""
        if "portfolios" in context and isinstance(context["portfolios"], list):
            return context["portfolios"]
        if "portfolio" in context and isinstance(context["portfolio"], dict):
            return [context["portfolio"]]

        portfolios: list[dict[str, Any]] = []

        # 1. Try ~/.flowcore/portfolios.json
        p_file = _DATA_DIR / "portfolios.json"
        if p_file.exists():
            try:
                data = json.loads(p_file.read_text(encoding="utf-8"))
                if isinstance(data, list) and data:
                    portfolios.extend(data)
            except Exception as e:
                logger.warning("Could not parse ~/.flowcore/portfolios.json: {}", e)

        # 2. Try bundled reference portfolio or sample portfolios
        if not portfolios:
            ref_file = _CONFIG_DIR / "portfolio_moderate_1m.json"
            if ref_file.exists():
                try:
                    ref_data = json.loads(ref_file.read_text(encoding="utf-8"))
                    if isinstance(ref_data, dict):
                        portfolios.append(ref_data)
                except Exception as e:
                    logger.warning("Could not parse reference portfolio: {}", e)

        # 3. Default fallback sample portfolios if none had positions defined
        if not portfolios:
            portfolios = [self._default_sample_portfolio()]

        return portfolios

    def evaluate_portfolio(self, portfolio: dict[str, Any]) -> list[dict[str, Any]]:
        """Evaluate a single portfolio and return a list of compliance violations."""
        client_id = str(portfolio.get("id", "carteira-1"))
        client_name = portfolio.get("name", "Cliente Sem Nome")

        target_alloc = portfolio.get("target_allocation", [])
        current_alloc = portfolio.get("current_allocation", {})
        sleeve_limits = portfolio.get("sleeve_limits", {})

        violations: list[dict[str, Any]] = []

        # If current_allocation is empty, check if sample current positions were provided in portfolio
        if not current_alloc and portfolio.get("sample_current_positions"):
            current_alloc = portfolio.get("sample_current_positions", {})

        # Compute current weights per high-level class / category
        current_totals: dict[str, float] = {}
        if current_alloc:
            for key, val in current_alloc.items():
                current_totals[key] = float(val)

        # If current_alloc is missing, construct from holdings or check target allocation drift
        if not current_alloc and target_alloc:
            # Check if drift is directly specified in target items
            for item in target_alloc:
                item_id = item.get("id")
                cls = item.get("class", item_id)
                curr_w = float(item.get("current_weight", item.get("weight", 0)))
                current_totals[cls] = current_totals.get(cls, 0.0) + curr_w

        # Group into primary categories: RV (Renda Variável), RF (Renda Fixa), AI Theme, Alternativos
        rv_current = sum(v for k, v in current_totals.items() if "renda_variavel" in k or "equity" in k or k == "RV")
        rf_current = sum(v for k, v in current_totals.items() if "renda_fixa" in k or "fixed" in k or k == "RF")
        ai_current = current_totals.get("ai_theme", current_totals.get("renda_variavel_tematica", 0.0))
        alt_current = sum(v for k, v in current_totals.items() if "alternativos" in k or "alt" in k)

        # Rule 1: Renda Variável Limit Check
        rv_limit = float(sleeve_limits.get("renda_variavel_max", portfolio.get("rv_limit", 30.0)))
        if rv_current > rv_limit:
            diff = round(rv_current - rv_limit, 2)
            severity = "CRITICAL" if diff >= 5.0 else "WARNING"
            violations.append({
                "client_id": client_id,
                "client_name": client_name,
                "type": "EXCESSO_RV",
                "current": round(rv_current, 2),
                "limit": round(rv_limit, 2),
                "diff": diff,
                "severity": severity,
                "message": f"Renda variável {diff} p.p. acima do limite de {rv_limit}%.",
                "suggested_action": f"Rebalancear vendendo {diff} p.p. de Renda Variável para reenquadrar ao limite.",
            })

        # Rule 2: Renda Fixa Minimum Limit Check
        rf_min = float(sleeve_limits.get("renda_fixa_total_min", portfolio.get("rf_min_limit", 55.0)))
        if rf_current < rf_min and rf_current > 0:
            diff = round(rf_min - rf_current, 2)
            severity = "CRITICAL" if diff >= 5.0 else "WARNING"
            violations.append({
                "client_id": client_id,
                "client_name": client_name,
                "type": "DEFICIT_RF",
                "current": round(rf_current, 2),
                "limit": round(rf_min, 2),
                "diff": diff,
                "severity": severity,
                "message": f"Renda fixa {diff} p.p. abaixo do limite mínimo de {rf_min}%.",
                "suggested_action": f"Aumentar alocação em Renda Fixa em {diff} p.p.",
            })

        # Rule 3: AI Theme Satellite Limit Check
        ai_limit = float(sleeve_limits.get("ai_theme_max", 10.0))
        if ai_current > ai_limit:
            diff = round(ai_current - ai_limit, 2)
            severity = "CRITICAL" if diff >= 3.0 else "WARNING"
            violations.append({
                "client_id": client_id,
                "client_name": client_name,
                "type": "EXCESSO_IA",
                "current": round(ai_current, 2),
                "limit": round(ai_limit, 2),
                "diff": diff,
                "severity": severity,
                "message": f"Exposição ao tema IA ({ai_current}%) excede o limite máximo de {ai_limit}%.",
                "suggested_action": f"Reduzir exposição em ativos de IA em {diff} p.p.",
            })

        # Rule 4: Alternativos Limit Check
        alt_limit = float(sleeve_limits.get("alternativos_max", 7.0))
        if alt_current > alt_limit:
            diff = round(alt_current - alt_limit, 2)
            severity = "CRITICAL" if diff >= 3.0 else "WARNING"
            violations.append({
                "client_id": client_id,
                "client_name": client_name,
                "type": "EXCESSO_ALT",
                "current": round(alt_current, 2),
                "limit": round(alt_limit, 2),
                "diff": diff,
                "severity": severity,
                "message": f"Ativos alternativos ({alt_current}%) excedem o limite de {alt_limit}%.",
                "suggested_action": f"Rebalancear reduzindo {diff} p.p. em alternativos.",
            })

        return violations

    @staticmethod
    def _default_sample_portfolio() -> dict[str, Any]:
        return {
            "id": "cliente-001",
            "name": "Carteira Moderada — R$ 1 milhão",
            "current_allocation": {
                "renda_variavel_brasil": 15.0,
                "renda_variavel_global": 16.0,
                "renda_variavel_tematica": 7.0,
                "renda_fixa_brasil": 45.0,
                "renda_fixa_internacional": 10.0,
                "alternativos": 7.0,
            },
            "sleeve_limits": {
                "renda_variavel_max": 30.0,
                "renda_fixa_total_min": 55.0,
                "ai_theme_max": 10.0,
                "alternativos_max": 7.0,
            },
        }
