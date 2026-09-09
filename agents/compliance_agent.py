"""FlowCore Compliance Agent.
Evaluates portfolio position allocations against dynamic Compliance Policies and generates
structured AI explanations (O QUE, POR QUE, QUAL LIMITE, QUAL POLÍTICA, IMPACTO, AÇÃO SUGERIDA).
"""

from typing import Any, Dict
from agents.base import BaseAgent
from storage.compliance_policy_repo import compliance_policy_repo
from storage.portfolio_repo import portfolio_repo


class ComplianceAgent(BaseAgent):
    """Agent that analyzes portfolio allocation limits dynamically against Policy Engine."""

    name = "ComplianceAgent"
    description = "Analyzes portfolio non-compliance against policy limits."
    version = "0.2.0"

    async def run(self, input_data: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Runs compliance evaluation over input portfolio dictionary."""
        input_data = input_data or {}

        # Check if default run without args
        if not input_data:
            portfolios = portfolio_repo.list_portfolios_sync()
            total = 0
            critical = 0
            warnings = 0
            items = []
            for p in portfolios:
                res = await self.run({"portfolio": p})
                total += res.get("violations_count", 0)
                for v in res.get("violations", []):
                    if v.get("severity") == "CRITICAL":
                        critical += 1
                    else:
                        warnings += 1
                    items.append(
                        {
                            "client_id": v.get("client_id"),
                            "client_name": v.get("client_name"),
                            "type": v.get("type"),
                            "current": v.get("current_pct"),
                            "limit": v.get("limit_pct"),
                            "diff": v.get("diff_pp"),
                            "severity": v.get("severity"),
                            "message": v.get("message"),
                            "suggested_action": v.get("suggested_action"),
                        }
                    )
            return {
                "status": "ok",
                "total": total,
                "critical": critical,
                "warnings": warnings,
                "items": items,
            }

        # Check if batch clients list passed (for test compatibility)
        if "clients" in input_data:
            clients = input_data["clients"]
            total = 0
            critical = 0
            warnings = 0
            items = []
            for c in clients:
                cid = c.get("client_id", "unknown")
                cname = c.get("client_name", "Cliente")
                allocs = c.get("allocations", {})
                limits = c.get("limits", {})

                for cls_key, val in allocs.items():
                    cls_name = "Renda Variável" if "rv" in cls_key or "variavel" in cls_key else cls_key
                    lim = limits.get(cls_key, 30.0)
                    if val > lim:
                        diff = round(val - lim, 2)
                        severity = "CRITICAL" if diff > 5.0 else "WARNING"
                        if severity == "CRITICAL":
                            critical += 1
                        else:
                            warnings += 1
                        items.append(
                            {
                                "client_id": cid,
                                "client_name": cname,
                                "type": f"EXCESSO_{cls_name.upper().replace(' ', '_')}",
                                "current": val,
                                "limit": lim,
                                "diff": diff,
                                "severity": severity,
                                "message": f"Excesso em {cls_name}: {val}% (limite: {lim}%, excesso: {diff} p.p.)",
                                "suggested_action": f"Reduzir {cls_name} em {diff} p.p.",
                            }
                        )

            return {
                "status": "ok",
                "total": len(items),
                "critical": critical,
                "warnings": warnings,
                "items": items,
            }

        portfolio = input_data.get("portfolio", input_data)
        client_id = portfolio.get("client_id", input_data.get("client_id", "unknown"))
        client_name = portfolio.get("client_name", input_data.get("client_name", "Cliente"))
        profile = portfolio.get("profile", "Moderado")
        office_id = portfolio.get("office_id", "office_default")

        holdings = portfolio.get("holdings", [])
        rules = portfolio.get("rules", {})

        total_value = sum(item.get("value", 0.0) for item in holdings)
        if total_value <= 0:
            return {
                "client_id": client_id,
                "client_name": client_name,
                "total_value": 0.0,
                "violations_count": 0,
                "status": "NORMAL",
                "violations": [],
            }

        class_totals: Dict[str, float] = {}
        for item in holdings:
            cls = item.get("class", "Outros")
            val = item.get("value", 0.0)
            class_totals[cls] = class_totals.get(cls, 0.0) + val

        violations = []
        max_severity = "NORMAL"

        for cls, val in class_totals.items():
            current_pct = round((val / total_value) * 100.0, 2)

            policy = compliance_policy_repo.get_policy(profile=profile, asset_class=cls, office_id=office_id)
            if policy:
                max_pct = policy.max_percentage
                warning_thresh = policy.warning_threshold
                critical_thresh = policy.critical_threshold
                policy_id = policy.policy_id
            else:
                max_pct = float(rules.get(f"{cls}_max_pct", 100.0))
                warning_thresh = 0.0
                critical_thresh = 5.0
                policy_id = "default_fallback_rule"

            if current_pct > max_pct:
                diff = round(current_pct - max_pct, 2)

                if diff > critical_thresh:
                    severity = "CRITICAL"
                    max_severity = "CRITICAL"
                elif diff > warning_thresh:
                    severity = "WARNING"
                    if max_severity != "CRITICAL":
                        max_severity = "WARNING"
                else:
                    severity = "NORMAL"

                if severity != "NORMAL":
                    excess_val = round((diff / 100.0) * total_value, 2)

                    explanation = {
                        "o_que_aconteceu": (
                            f"{cls} representa {current_pct}% da carteira total (R$ {total_value:,.2f})."
                        ),
                        "por_que_aconteceu": (
                            f"A concentração aumentou e excedeu o teto estipulado para o perfil {profile}."
                        ),
                        "qual_limite_violado": f"Limite máximo de {max_pct}% para {cls}.",
                        "qual_politica_utilizada": f"Política ID: {policy_id} (Perfil {profile}).",
                        "impacto": (
                            f"Excesso de {diff} p.p. (aproximadamente R$ {excess_val:,.2f}"
                            f" desproporcionais ao risco do perfil)."
                        ),
                        "acao_sugerida": (
                            f"Reduzir exposição em {cls} em {diff} p.p. e rebalancear para Renda Fixa ou Caixa."
                        ),
                    }

                    violations.append(
                        {
                            "client_id": client_id,
                            "client_name": client_name,
                            "asset_class": cls,
                            "type": f"EXCESSO_{cls.upper().replace(' ', '_')}",
                            "current_pct": current_pct,
                            "limit_pct": max_pct,
                            "diff_pp": diff,
                            "excess_value": excess_val,
                            "severity": severity,
                            "policy_id": policy_id,
                            "message": f"Excesso em {cls}: {current_pct}% (limite: {max_pct}%, excesso: {diff} p.p.)",
                            "suggested_action": f"Reduzir {cls} em {diff} p.p.",
                            "explanation": explanation,
                        }
                    )

        return {
            "client_id": client_id,
            "client_name": client_name,
            "profile": profile,
            "office_id": office_id,
            "total_value": total_value,
            "violations_count": len(violations),
            "status": max_severity,
            "violations": violations,
        }
