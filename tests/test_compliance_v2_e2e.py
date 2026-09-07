"""FlowCore Autonomous Desenquadramento V2 End-to-End Simulation Test.
Simulates Maria's scenario (1M portfolio, 38% RV vs 30% limit) across Event Bus,
Compliance Agent, Rebalancing Agent, HITL Approval, Operations Workflow, and final Reenquadramento.
"""

import pytest
from agents.compliance_events import event_bus, FlowCoreEvent, EventType
from agents.compliance_orchestrator import orchestrator
from storage.compliance_case_repo import compliance_case_repo, CaseStatus
from storage.compliance_policy_repo import compliance_policy_repo


def test_e2e_maria_desenquadramento_flow():
    # Reset event bus state
    event_bus.clear()

    # Maria's non-compliant portfolio (R$ 1,000,000 Total, 38% RV vs 30% limit)
    maria_portfolio = {
        "id": "port_maria_001",
        "client_id": "maria_oliveira",
        "client_name": "Maria Oliveira",
        "profile": "Moderado",
        "holdings": [
            {"asset": "PETR4", "class": "Renda Variável", "value": 380000.0},
            {"asset": "CDB Itaú", "class": "Renda Fixa", "value": 420000.0},
            {"asset": "IVVB11", "class": "Internacional", "value": 100000.0},
            {"asset": "Caixa", "class": "Caixa", "value": 100000.0},
        ],
    }

    # Step 1: Fire PORTFOLIO_CHANGED event
    port_event = FlowCoreEvent(
        event_type=EventType.PORTFOLIO_CHANGED,
        client_id="maria_oliveira",
        portfolio_id="port_maria_001",
        source="PortfolioService",
        payload={"portfolio": maria_portfolio},
    )

    result = orchestrator.handle_portfolio_changed(port_event)

    # Verify detection
    assert result["status"] == "NON_COMPLIANT"
    assert result["severity"] == "CRITICAL"
    case_id = result["case_id"]

    # Step 2: Verify persistent ComplianceCase created
    case = compliance_case_repo.get_by_id(case_id)
    assert case is not None
    assert case.status == CaseStatus.WAITING_APPROVAL
    assert case.difference == 8.0  # 38% - 30%
    assert case.proposed_rebalancing["proposed"] is True
    assert case.ai_explanation["qual_limite_violado"] == "Limite máximo de 30.0% para Renda Variável."

    # Step 3: Simulate Advisor HITL Approval
    rebalanced_maria_portfolio = {
        "id": "port_maria_001",
        "client_id": "maria_oliveira",
        "client_name": "Maria Oliveira",
        "profile": "Moderado",
        "holdings": [
            {"asset": "PETR4", "class": "Renda Variável", "value": 300000.0},  # Reduced to 30%
            {"asset": "CDB Itaú", "class": "Renda Fixa", "value": 500000.0},  # Increased to 50%
            {"asset": "IVVB11", "class": "Internacional", "value": 100000.0},
            {"asset": "Caixa", "class": "Caixa", "value": 100000.0},
        ],
    }

    approval_event = FlowCoreEvent(
        event_type=EventType.REBALANCING_APPROVED,
        client_id="maria_oliveira",
        portfolio_id="port_maria_001",
        source="AdvisorHITL",
        payload={
            "case_id": case_id,
            "approved_by": "Advisor Carlos",
            "updated_portfolio": rebalanced_maria_portfolio,
        },
        correlation_id=port_event.correlation_id,
    )

    final_result = orchestrator.handle_rebalancing_approved(approval_event)

    # Step 4: Verify post-execution confirmation & case resolution
    assert final_result["status"] == "COMPLIANT"
    updated_case = compliance_case_repo.get_by_id(case_id)
    assert updated_case.status == CaseStatus.RESOLVED
    assert updated_case.resolved_by == "System / ComplianceOrchestrator"

    # Verify PORTFOLIO_REENQUADRED published to Audit Log
    audit_log = event_bus.get_audit_log()
    event_types = [e["event_type"] for e in audit_log]
    assert EventType.PORTFOLIO_REENQUADRED in event_types
