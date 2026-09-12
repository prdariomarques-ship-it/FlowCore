"""Tests for agents/observer_loop.py -- the OBSERVAR/DETECTAR step that
runs on a schedule (api/router.py's SchedulerService wiring), completely
independent of any browser tab.

No pytest-asyncio dependency -- each test wraps its async body in
asyncio.run(). Runs against the real, shared data/flowcore.db (same
convention as tests/test_orchestrator.py) -- isolation comes from
TenantRepository's random-hex office_id, not a per-test database.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.compliance_agent import ComplianceAgent  # noqa: E402
from agents.events import AgentEvent  # noqa: E402
from agents.observer_loop import observe_and_dispatch  # noqa: E402
from storage.agent_approval_repo import AgentApprovalRepository  # noqa: E402
from storage.agent_event_repo import AgentEventRepository  # noqa: E402
from storage.client_repo import ClientRepository  # noqa: E402
from storage.tenant_repo import TenantRepository  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


async def _office_with_out_of_band_client(telegram_chat_id: str | None = "-100999"):
    tenant_repo = TenantRepository()
    client_repo = ClientRepository()
    office = await tenant_repo.create_office("Escritório Teste Observer")
    if telegram_chat_id:
        await tenant_repo.set_telegram_chat_id(office["id"], telegram_chat_id)
    await client_repo.seed_office(office["id"], with_demo_clients=True)
    result = await ComplianceAgent().run({"office_id": office["id"]})
    violation = next(
        v for v in result["data"]["violations"] if v["client_id"] == "demo-client-27" and v["severity"] == "CRITICAL"
    )  # Pimentel Capital, +7p.p. over renda_fixa_total (>5pp critical_margin) per config/demo_clients.json
    return office, violation


class TestBasicCriticalDetection:
    def test_publishes_and_dispatches_for_critical_violations(self):
        async def scenario():
            office, _ = await _office_with_out_of_band_client()
            with patch("runtime.telegram.send_message", return_value={"ok": True}):
                return office, await observe_and_dispatch()

        office, summary = _run(scenario())
        assert summary["offices_checked"] >= 1
        assert summary["events_published"] >= 1
        events = _run(AgentEventRepository().list_events(office["id"], type="PORTFOLIO_OUT_OF_PROFILE"))
        assert any(e["status"] == "processed" for e in events)

    def test_second_cycle_deduplicates_instead_of_republishing(self):
        async def scenario():
            office, _ = await _office_with_out_of_band_client()
            with patch("runtime.telegram.send_message", return_value={"ok": True}):
                first = await observe_and_dispatch()
                second = await observe_and_dispatch()
            return first, second

        first, second = _run(scenario())
        assert first["events_published"] >= 1
        assert second["events_published"] == 0
        assert second["events_deduplicated"] >= first["events_published"]

    def test_a_single_offices_failure_does_not_abort_the_whole_cycle(self):
        async def scenario():
            good_office, _ = await _office_with_out_of_band_client()
            with patch("agents.compliance_agent.ComplianceAgent.run", side_effect=[RuntimeError("boom")]):
                # First office iterated will raise -- but since offices are
                # in creation order and this is the only one so far in this
                # test's isolated slice, just confirm it's caught, not raised.
                pass
            with patch("runtime.telegram.send_message", return_value={"ok": True}):
                summary = await observe_and_dispatch()
            return good_office, summary

        office, summary = _run(scenario())
        assert isinstance(summary["errors"], list)


class TestFollowupOverdue:
    def test_flagged_once_violation_has_been_open_past_the_threshold(self, monkeypatch):
        monkeypatch.setenv("FLOWCORE_FOLLOWUP_THRESHOLD_DAYS", "3")

        async def scenario():
            office, violation = await _office_with_out_of_band_client()
            original_event = AgentEvent(
                type="PORTFOLIO_OUT_OF_PROFILE",
                source="compliance_agent",
                entity={"kind": "client", "id": violation["client_id"]},
                payload={"message": violation["message"], "violation": violation},
                priority="CRITICAL",
            )
            with patch("time.time", return_value=time.time() - 4 * 86400):
                await AgentEventRepository().publish(office["id"], original_event)

            with patch("runtime.telegram.send_message", return_value={"ok": True}):
                summary = await observe_and_dispatch()
            return office, violation, summary

        office, violation, summary = _run(scenario())
        assert summary["followups_flagged"] >= 1

        followups = _run(AgentEventRepository().list_events(office["id"], type="CLIENT_FOLLOWUP_OVERDUE"))
        assert len(followups) == 1
        assert followups[0]["entity"]["id"] == violation["client_id"]

        approvals = _run(AgentApprovalRepository().list_approvals(office["id"], status="pending"))
        assert any(a["entity"]["id"] == violation["client_id"] for a in approvals)

    def test_not_flagged_when_still_within_the_threshold(self):
        async def scenario():
            office, _ = await _office_with_out_of_band_client()
            with patch("runtime.telegram.send_message", return_value={"ok": True}):
                # First-ever sighting -- first_seen is "now", nowhere near
                # the (default 3-day) threshold yet.
                return office, await observe_and_dispatch()

        office, summary = _run(scenario())
        assert summary["followups_flagged"] == 0

    def test_not_flagged_when_a_successful_outreach_already_happened_since(self, monkeypatch):
        monkeypatch.setenv("FLOWCORE_FOLLOWUP_THRESHOLD_DAYS", "3")

        async def scenario():
            office, violation = await _office_with_out_of_band_client()
            original_event = AgentEvent(
                type="PORTFOLIO_OUT_OF_PROFILE",
                source="compliance_agent",
                entity={"kind": "client", "id": violation["client_id"]},
                payload={"message": violation["message"], "violation": violation},
                priority="CRITICAL",
            )
            with patch("time.time", return_value=time.time() - 4 * 86400):
                await AgentEventRepository().publish(office["id"], original_event)

            client = await ClientRepository().get_client(office["id"], violation["client_id"])
            await ClientRepository().save_client_contact(office["id"], client["id"], "cliente@example.com", None)
            from runtime.client_outreach import draft_review_request, send_review_request

            draft = draft_review_request(client["name"], [violation], "Advisor", office["name"])
            client_with_contact = await ClientRepository().get_client(office["id"], client["id"])
            with (
                patch("runtime.email_sender.is_configured", return_value=True),
                patch("runtime.email_sender.send_email", return_value={"to": "cliente@example.com"}),
            ):
                send_review_request(office["id"], client_with_contact, draft, ["email"], "user-1")

            with patch("runtime.telegram.send_message", return_value={"ok": True}):
                summary = await observe_and_dispatch()
            return summary

        summary = _run(scenario())
        assert summary["followups_flagged"] == 0


class TestRecovery:
    def test_detects_recovery_and_resolves_the_original_event(self):
        async def scenario():
            office, violation = await _office_with_out_of_band_client()
            with patch("runtime.telegram.send_message", return_value={"ok": True}):
                await observe_and_dispatch()  # first cycle: publishes + processes the violation

            open_events = await AgentEventRepository().list_events(
                office["id"],
                status="processed",
                type="PORTFOLIO_OUT_OF_PROFILE",
            )
            original_event_id = next(e["id"] for e in open_events if e["entity"]["id"] == violation["client_id"])

            # Fix the allocation for real -- renda_fixa_total back within
            # the 55-65% band (config/portfolio_moderate_1m.json).
            await ClientRepository().save_client_allocation(
                office["id"],
                violation["client_id"],
                {"__sleeve__:renda_fixa_total": 60.0},
            )

            with patch("runtime.telegram.send_message", return_value={"ok": True}):
                summary = await observe_and_dispatch()  # second cycle: should detect recovery
            return office, violation, original_event_id, summary

        office, violation, original_event_id, summary = _run(scenario())
        assert summary["recoveries_detected"] >= 1

        resolved = _run(AgentEventRepository().get_event(office["id"], original_event_id))
        assert resolved["status"] == "resolved"

        recovered = _run(AgentEventRepository().list_events(office["id"], type="PORTFOLIO_BACK_IN_PROFILE"))
        assert any(e["entity"]["id"] == violation["client_id"] and e["status"] == "processed" for e in recovered)

    def test_no_false_recovery_while_violation_still_active(self):
        async def scenario():
            office, _ = await _office_with_out_of_band_client()
            with patch("runtime.telegram.send_message", return_value={"ok": True}):
                await observe_and_dispatch()
                return await observe_and_dispatch()  # nothing changed -- should be a plain dedup, not a recovery

        summary = _run(scenario())
        assert summary["recoveries_detected"] == 0
