"""Tests for ApprovalManager."""

import pytest
from runtime.approval.manager import ApprovalManager

def test_approval_manager(tmp_path):
    storage = tmp_path / "approvals.json"
    mgr = ApprovalManager(storage_file=storage)

    req = mgr.request_approval(
        agent_id="follow_up_agent",
        title="Enviar mensagem WhatsApp ao cliente cli_002",
        description="Follow-up de inatividade de 74 dias",
        action_type="SEND_MESSAGE",
        payload={"client_id": "cli_002", "message": "Olá!"},
    )

    assert req["status"] == "PENDING"
    pending = mgr.list_pending_approvals()
    assert len(pending) == 1

    resolved = mgr.resolve_approval(req["id"], approved=True, user="advisor_1")
    assert resolved["status"] == "APPROVED"
    assert len(mgr.list_pending_approvals()) == 0
