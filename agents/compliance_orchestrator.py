"""FlowCore Compliance Orchestrator.
Orchestrates events, agents (Compliance, Rebalancing), persistent ComplianceCases,
HITL state transitions, and post-execution feedback loops with max_iterations safety guards.
"""

import asyncio
from typing import Any, Dict
from agents.compliance_agent import ComplianceAgent
from agents.rebalancing_agent import RebalancingAgent
from agents.compliance_events import FlowCoreEvent, EventType, event_bus
from storage.compliance_case_repo import compliance_case_repo, ComplianceCase, CaseStatus


class ComplianceOrchestrator:
    """Central orchestrator for autonomous portfolio non-compliance monitoring and resolution."""

    def __init__(self, max_iterations: int = 3):
        self.compliance_agent = ComplianceAgent()
        self.rebalancing_agent = RebalancingAgent()
        self.max_iterations = max_iterations
        self._iteration_counters: Dict[str, int] = {}
        self._register_listeners()

    def _register_listeners(self):
        event_bus.subscribe(EventType.PORTFOLIO_CHANGED, self.handle_portfolio_changed)
        event_bus.subscribe(EventType.POSITION_CHANGED, self.handle_portfolio_changed)
        event_bus.subscribe(EventType.REBALANCING_APPROVED, self.handle_rebalancing_approved)

    def _run_async_agent(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import nest_asyncio

            nest_asyncio.apply()
            return loop.run_until_complete(coro)
        else:
            return asyncio.run(coro)

    def handle_portfolio_changed(self, event: FlowCoreEvent) -> Dict[str, Any]:
        """Triggered when a portfolio or position changes."""
        portfolio = event.payload.get("portfolio", {})
        client_id = event.client_id
        portfolio_id = event.portfolio_id
        correlation_id = event.correlation_id

        # Track iteration count to prevent infinite loops
        counter_key = f"{portfolio_id}_{correlation_id}"
        current_iter = self._iteration_counters.get(counter_key, 0) + 1
        self._iteration_counters[counter_key] = current_iter

        if current_iter > self.max_iterations:
            return {
                "status": "STOPPED_MAX_ITERATIONS",
                "message": (
                    f"Orchestrator atingiu o limite de {self.max_iterations}"
                    f" iterações para correlation {correlation_id}."
                ),
            }

        # Run Compliance Agent
        eval_res = self._run_async_agent(self.compliance_agent.run({"portfolio": portfolio, "client_id": client_id}))
        violations = eval_res.get("violations", [])

        if not violations:
            # Check if there was an open case for this portfolio and mark RESOLVED
            open_cases = compliance_case_repo.list_cases(client_id=client_id)
            for case in open_cases:
                if case.status in [CaseStatus.OPEN, CaseStatus.WAITING_APPROVAL, CaseStatus.APPROVED]:
                    case.status = CaseStatus.RESOLVED
                    case.resolved_by = "System / ComplianceOrchestrator"
                    compliance_case_repo.save(case)

                    # Publish PORTFOLIO_REENQUADRED
                    reenquadred_event = FlowCoreEvent(
                        event_type=EventType.PORTFOLIO_REENQUADRED,
                        client_id=client_id,
                        portfolio_id=portfolio_id,
                        source="ComplianceOrchestrator",
                        payload={"message": "Carteira reenquadrada com sucesso.", "case_id": case.id},
                        correlation_id=correlation_id,
                    )
                    event_bus.publish(reenquadred_event)

            return {
                "status": "COMPLIANT",
                "message": "Carteira em conformidade.",
                "violations_count": 0,
            }

        # Violations found -> Create or update Compliance Case
        v = violations[0]  # Focus primary violation
        case_id = f"case_{client_id}_{v.get('asset_class', 'RV').lower().replace(' ', '_')}"

        # Prepare rebalancing proposal
        reb_res = self._run_async_agent(self.rebalancing_agent.run({"portfolio": portfolio, "violations": violations}))

        existing_case = compliance_case_repo.get_by_id(case_id)
        if existing_case and existing_case.status in [CaseStatus.WAITING_APPROVAL, CaseStatus.APPROVED]:
            case_status = existing_case.status
        else:
            case_status = CaseStatus.WAITING_APPROVAL

        new_case = ComplianceCase(
            id=case_id,
            client_id=client_id,
            portfolio_id=portfolio_id,
            type=v.get("type", "DESENQUADRAMENTO"),
            severity=v.get("severity", "CRITICAL"),
            current_value=v.get("current_pct", 0.0),
            limit_value=v.get("limit_pct", 0.0),
            difference=v.get("diff_pp", 0.0),
            policy_id=v.get("policy_id", "pol_default"),
            reason=v.get("message", "Desvio de alocação de ativos."),
            suggested_action=v.get("suggested_action", "Rebalancear carteira."),
            status=case_status,
            proposed_rebalancing=reb_res,
            ai_explanation=v.get("explanation"),
        )
        compliance_case_repo.save(new_case)

        # Publish COMPLIANCE_ALERT_CREATED & REBALANCING_PROPOSED
        alert_event = FlowCoreEvent(
            event_type=EventType.COMPLIANCE_ALERT_CREATED,
            client_id=client_id,
            portfolio_id=portfolio_id,
            source="ComplianceOrchestrator",
            payload={"case": new_case.to_dict()},
            correlation_id=correlation_id,
        )
        event_bus.publish(alert_event)

        proposal_event = FlowCoreEvent(
            event_type=EventType.REBALANCING_PROPOSED,
            client_id=client_id,
            portfolio_id=portfolio_id,
            source="RebalancingAgent",
            payload={"proposal": reb_res, "case_id": case_id},
            correlation_id=correlation_id,
        )
        event_bus.publish(proposal_event)

        return {
            "status": "NON_COMPLIANT",
            "case_id": case_id,
            "severity": v.get("severity"),
            "violations": violations,
            "rebalancing_proposal": reb_res,
        }

    def handle_rebalancing_approved(self, event: FlowCoreEvent) -> Dict[str, Any]:
        """Triggered when advisor approves HITL rebalancing."""
        case_id = event.payload.get("case_id")
        user = event.payload.get("approved_by", "Advisor")
        updated_portfolio = event.payload.get("updated_portfolio")

        case = compliance_case_repo.get_by_id(case_id) if case_id else None
        if case:
            case.status = CaseStatus.APPROVED
            case.resolved_by = user
            compliance_case_repo.save(case)

        # Re-evaluate compliance using updated portfolio to close feedback loop
        if updated_portfolio:
            new_port_event = FlowCoreEvent(
                event_type=EventType.PORTFOLIO_CHANGED,
                client_id=event.client_id,
                portfolio_id=event.portfolio_id,
                source="OperationsWorkflow",
                payload={"portfolio": updated_portfolio},
                correlation_id=event.correlation_id,
            )
            return self.handle_portfolio_changed(new_port_event)

        return {"status": "APPROVED", "case_id": case_id}


orchestrator = ComplianceOrchestrator()
