"""FlowCore Compliance Agent — portfolio allocation drift ("desenquadramento").

Compares a portfolio's current allocation against its target sleeve limits
and classifies each sleeve as NORMAL / WARNING / CRITICAL. This is the first
agent of the "Investment Copilot" direction: monitor carteiras and alert on
desenquadramento, nothing more for this MVP.

Fase 0 (multi-office architecture): every evaluation is scoped to one
office. `context["office_id"]` is required — there is no longer a
single installation-wide default to silently fall back to, because that
would mean office B's alerts endpoint could return office A's clients.
Every caller of `run()` (dashboard_routes.py, IntelligenceEngine,
PriorityEngine, tests) must resolve office_id from the authenticated
session (api.tenant_auth.get_current_user) and pass it explicitly.

Data sources — both real, nothing here is invented:
- runtime/portfolio/reference.py: the office's investment policy
  (target_allocation + sleeve_limits + review_policy), editable via PUT
  /api/portfolio/reference. `current_allocation` lives on this same
  object and stays unset until someone actually sets it — never guessed.
- runtime/portfolio/demo_clients.py: per-office example/real clients,
  each carrying their own current_allocation, evaluated against the same
  office's policy.

NOTE — storage/portfolio_repo.py's PortfolioRepository (the single
user's own personal brokerage holdings, pre-dating multi-tenancy) is
deliberately NOT merged in here anymore: it has no office_id column yet,
so folding it in would leak the same rows into every office's alerts —
exactly the isolation bug fase 0 exists to prevent. Making that
repository office-aware is a real follow-up (add an office_id column,
thread it through storage/portfolio_repo.py), not something to paper
over here.

A portfolio this agent cannot evaluate is reported with an honest status
(SEM_POSICAO_ATUAL / SEM_REGRAS_DEFINIDAS) and an empty violation list —
never a guessed position or a fabricated limit. Callers that already
have a one-off current_allocation (e.g. a manual test) can also pass it
in via `context["portfolios"]` without persisting anything.
"""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from runtime.portfolio.reference import load_reference_portfolio

_DEFAULT_CRITICAL_MARGIN_POINTS = 5.0

# Which target_allocation `class` values roll up into each sleeve_limits key.
# This mirrors portfolio_moderate_1m.json's own policy — not a new
# classification invented for this agent.
_SLEEVE_CLASS_ROLLUPS: dict[str, set[str]] = {
    "renda_fixa_total": {"renda_fixa_brasil", "renda_fixa_internacional"},
    "alternativos": {"alternativos"},
}
# ai_theme and the liquidity reserve are single target_allocation line
# items, not a class rollup, so they're matched by id instead.
_AI_THEME_ITEM_ID = "ai_theme"
_LIQUIDITY_ITEM_ID = "br_fixed_liquidity"


class ComplianceAgent(BaseAgent):
    name = "compliance"
    description = "Detecta desenquadramento de carteira: posição atual vs. limites de alocação"
    version = "0.1.0"

    async def run(self, context: dict | None = None) -> dict[str, Any]:
        context = context or {}
        portfolios = context.get("portfolios")
        if portfolios is None:
            office_id = context.get("office_id")
            if not office_id:
                raise ValueError("ComplianceAgent.run() requires context['office_id']")
            portfolios = await self._load_registered_portfolios(office_id)

        results = [self._evaluate_portfolio(p) for p in portfolios]
        violations = [v for r in results for v in r["violations"]]
        return {
            "status": "ok",
            "data": {
                "portfolios_evaluated": len(results),
                "violations": violations,
                "portfolios": results,
            },
        }

    # ── Data loading ─────────────────────────────────────────────────────────

    async def _load_registered_portfolios(self, office_id: str) -> list[dict[str, Any]]:
        """The portfolios this office actually has registered today.

        1. The office's investment policy (runtime/portfolio/reference.py)
           — the only one with a target_allocation/sleeve_limits policy.
           Real policy, but no current position until someone sets one,
           so it comes back with current_allocation=None until then.
        2. This office's clients (runtime/portfolio/demo_clients.py) — the
           27 fictitious examples for the bootstrap demo office, or real
           clients for any other office, each with their own position.
        """
        reference = await self._load_reference_portfolio(office_id)
        demo_clients = await self._load_demo_clients(office_id, reference)
        return [reference, *demo_clients]

    @staticmethod
    async def _load_demo_clients(office_id: str, reference: dict[str, Any]) -> list[dict[str, Any]]:
        """This office's clients — each evaluated against the same real
        investment policy as the office's reference portfolio
        (target_allocation/sleeve_limits/review_policy), but with their
        own current_allocation. Every result carries demo=True so nothing
        downstream can present a still-fictitious one as a real client."""
        try:
            from runtime.portfolio.demo_clients import load_demo_clients
        except Exception:
            return []
        clients = []
        for c in await load_demo_clients(office_id):
            clients.append(
                {
                    "id": c.get("id", ""),
                    "name": c.get("name", ""),
                    "target_allocation": reference["target_allocation"],
                    "sleeve_limits": reference["sleeve_limits"],
                    "review_policy": reference["review_policy"],
                    "current_allocation": c.get("current_allocation") or None,
                    "demo": bool(c.get("is_demo")),
                }
            )
        return clients

    @staticmethod
    async def _load_reference_portfolio(office_id: str) -> dict[str, Any]:
        data = await load_reference_portfolio(office_id)
        return {
            "id": data.get("id", "moderate-ia-1m"),
            "name": data.get("name", "Carteira Moderada — R$ 1 milhão"),
            "target_allocation": data.get("target_allocation", []),
            "sleeve_limits": data.get("sleeve_limits", {}),
            "review_policy": data.get("review_policy", {}),
            # Real once someone edits it via PUT /api/portfolio/reference
            # (runtime/portfolio/reference.py) — never guessed here.
            "current_allocation": data.get("current_allocation") or None,
        }

    # ── Evaluation ───────────────────────────────────────────────────────────

    def _evaluate_portfolio(self, portfolio: dict[str, Any]) -> dict[str, Any]:
        portfolio_id = portfolio.get("id", "")
        name = portfolio.get("name", portfolio_id)
        is_demo = bool(portfolio.get("demo"))

        if portfolio.get("_no_policy") or not portfolio.get("target_allocation"):
            return {
                "portfolio_id": portfolio_id,
                "portfolio_name": name,
                "status": "SEM_REGRAS_DEFINIDAS",
                "violations": [],
                "is_demo": is_demo,
            }

        current = portfolio.get("current_allocation")
        if not current:
            return {
                "portfolio_id": portfolio_id,
                "portfolio_name": name,
                "status": "SEM_POSICAO_ATUAL",
                "violations": [],
                "is_demo": is_demo,
            }

        target_allocation = portfolio["target_allocation"]
        sleeve_limits = portfolio.get("sleeve_limits", {})
        critical_margin = float(
            portfolio.get("review_policy", {}).get("critical_margin_points", _DEFAULT_CRITICAL_MARGIN_POINTS)
        )
        args = dict(portfolio_id=portfolio_id, portfolio_name=name, critical_margin=critical_margin, is_demo=is_demo)

        violations: list[dict[str, Any]] = []
        for sleeve_name, classes in _SLEEVE_CLASS_ROLLUPS.items():
            if f"{sleeve_name}_min" not in sleeve_limits and f"{sleeve_name}_max" not in sleeve_limits:
                continue
            item_ids = [i["id"] for i in target_allocation if i.get("class") in classes]
            current_sum = self._sleeve_current(sleeve_name, item_ids, current)
            violations.extend(
                self._check_band(
                    type_slug=sleeve_name.upper(),
                    label=sleeve_name.replace("_", " ").title(),
                    current=current_sum,
                    min_limit=sleeve_limits.get(f"{sleeve_name}_min"),
                    max_limit=sleeve_limits.get(f"{sleeve_name}_max"),
                    **args,
                )
            )

        ai_theme_item = next((i for i in target_allocation if i.get("id") == _AI_THEME_ITEM_ID), None)
        if ai_theme_item:
            violations.extend(
                self._check_band(
                    type_slug="AI_THEME",
                    label=ai_theme_item.get("label", _AI_THEME_ITEM_ID),
                    current=float(current.get(_AI_THEME_ITEM_ID, 0)),
                    min_limit=sleeve_limits.get("ai_theme_min"),
                    max_limit=sleeve_limits.get("ai_theme_max"),
                    **args,
                )
            )

        liquidity_item = next((i for i in target_allocation if i.get("id") == _LIQUIDITY_ITEM_ID), None)
        if liquidity_item:
            violations.extend(
                self._check_band(
                    type_slug="LIQUIDEZ",
                    label=liquidity_item.get("label", _LIQUIDITY_ITEM_ID),
                    current=float(current.get(_LIQUIDITY_ITEM_ID, 0)),
                    min_limit=sleeve_limits.get("liquidity_floor"),
                    max_limit=None,
                    **args,
                )
            )

        status = (
            "DESENQUADRADO"
            if any(v["severity"] == "CRITICAL" for v in violations)
            else "ATENCAO"
            if violations
            else "NORMAL"
        )
        return {
            "portfolio_id": portfolio_id,
            "portfolio_name": name,
            "status": status,
            "violations": violations,
            "is_demo": is_demo,
        }

    @staticmethod
    def _sleeve_current(sleeve_name: str, item_ids: list[str], current: dict[str, Any]) -> float:
        """Current weight for a multi-item sleeve (renda_fixa_total,
        alternativos): the sum of its constituent target_allocation items,
        UNLESS an explicit `__sleeve__:<name>` override is present.

        The override exists because these sleeves are not mutually
        exclusive at the item level — br_fixed_liquidity belongs to
        renda_fixa_brasil (rolls up into renda_fixa_total) AND is the item
        the liquidity floor checks. An editor who only thinks in terms of
        "my fixed income is at 47%, my liquidity reserve is at 8%" would
        otherwise double-count the liquidity item inside the fixed-income
        total the moment both are entered independently. The synthetic key
        lets the caller state the sleeve's aggregate directly and bypass
        item-level aggregation for that sleeve only — everything else
        (single-item sleeves like ai_theme/liquidity, or a caller that
        prefers to pass real item-level current_allocation, e.g. a test)
        is unaffected.
        """
        override_key = f"__sleeve__:{sleeve_name}"
        if override_key in current:
            return float(current[override_key])
        return sum(float(current.get(i, 0)) for i in item_ids)

    @staticmethod
    def _check_band(
        *,
        type_slug: str,
        label: str,
        current: float,
        min_limit: float | None,
        max_limit: float | None,
        critical_margin: float,
        portfolio_id: str,
        portfolio_name: str,
        is_demo: bool = False,
    ) -> list[dict[str, Any]]:
        """One-sided or two-sided band check against a real sleeve_limits entry.

        WARNING the moment current crosses the limit; CRITICAL once the
        overshoot itself exceeds critical_margin points (default 5pp) —
        e.g. limit=30%, current=32% -> WARNING; current=38% -> CRITICAL.
        """
        out: list[dict[str, Any]] = []
        if max_limit is not None and current > max_limit:
            diff = round(current - max_limit, 2)
            out.append(
                {
                    "client_id": portfolio_id,
                    "client_name": portfolio_name,
                    "type": f"EXCESSO_{type_slug}",
                    "current": round(current, 2),
                    "limit": max_limit,
                    "diff": diff,
                    "severity": "CRITICAL" if diff > critical_margin else "WARNING",
                    "message": f"{label} {diff:.1f} p.p. acima do limite ({current:.1f}% vs {max_limit:.1f}%).",
                    "is_demo": is_demo,
                }
            )
        if min_limit is not None and current < min_limit:
            diff = round(min_limit - current, 2)
            out.append(
                {
                    "client_id": portfolio_id,
                    "client_name": portfolio_name,
                    "type": f"ABAIXO_{type_slug}",
                    "current": round(current, 2),
                    "limit": min_limit,
                    "diff": diff,
                    "severity": "CRITICAL" if diff > critical_margin else "WARNING",
                    "message": f"{label} {diff:.1f} p.p. abaixo do piso ({current:.1f}% vs {min_limit:.1f}%).",
                    "is_demo": is_demo,
                }
            )
        return out
