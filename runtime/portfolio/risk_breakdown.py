"""Aggregate the reference portfolio's allocation into the four broad
categories the dashboard's "Risco da Carteira Agregada" donut shows:
Renda Fixa, Renda Variável, Multimercado, Alternativos.

Real data only — every category weight comes straight from
target_allocation's own `class` field (config/portfolio_moderate_1m.json),
the same real policy ComplianceAgent evaluates against, grouped the same
way its _SLEEVE_CLASS_ROLLUPS already groups renda_fixa_brasil +
renda_fixa_internacional into "renda_fixa_total". Unlike ComplianceAgent's
sleeve checks, these four categories are a strict partition of
target_allocation (every item's `class` belongs to exactly one category,
confirmed against the bundled portfolio), so summing current_allocation
by category can't double-count the way a sleeve override is needed for
(e.g. br_fixed_liquidity counted in both a class rollup and the liquidity
floor).

Uses current_allocation when the portfolio has one; otherwise falls back
to the target_allocation weights themselves, and says so explicitly via
`source` — never presents a target policy as if it were a live position.
"""
from __future__ import annotations

from typing import Any

from runtime.portfolio.reference import load_reference_portfolio

_CATEGORIES: dict[str, set[str]] = {
    "Renda Fixa": {"renda_fixa_brasil", "renda_fixa_internacional"},
    "Renda Variável": {"renda_variavel_brasil", "renda_variavel_global", "renda_variavel_tematica"},
    "Multimercado": {"multimercado"},
    "Alternativos": {"alternativos"},
}


async def compute_risk_breakdown(office_id: str) -> dict[str, Any]:
    portfolio = await load_reference_portfolio(office_id)
    target_allocation = portfolio.get("target_allocation", [])
    current_allocation = portfolio.get("current_allocation") or {}

    if not target_allocation:
        return {
            "portfolio_id": portfolio.get("id", "moderate-ia-1m"),
            "portfolio_name": portfolio.get("name", ""),
            "profile": portfolio.get("profile", ""),
            "source": "unavailable",
            "categories": [],
        }

    source = "current_allocation" if current_allocation else "target_allocation"
    categories = []
    for label, classes in _CATEGORIES.items():
        item_ids = [i["id"] for i in target_allocation if i.get("class") in classes]
        if current_allocation:
            weight = sum(float(current_allocation.get(i, 0)) for i in item_ids)
        else:
            weight = sum(float(i.get("weight", 0)) for i in target_allocation if i.get("class") in classes)
        categories.append({"label": label, "weight": round(weight, 2)})

    return {
        "portfolio_id": portfolio.get("id", "moderate-ia-1m"),
        "portfolio_name": portfolio.get("name", ""),
        "profile": portfolio.get("profile", ""),
        "source": source,
        "categories": categories,
    }
