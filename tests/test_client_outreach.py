"""Tests for runtime/client_outreach.py — drafting and sending client
review-request invitations (email + WhatsApp).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.client_outreach import draft_review_request, outreach_history, send_review_request  # noqa: E402

_VIOLATION = {
    "client_id": "c1",
    "client_name": "Família Teste",
    "type": "EXCESSO_AI_THEME",
    "current": 16.0,
    "limit": 10.0,
    "diff": 6.0,
    "severity": "CRITICAL",
    "message": "Tema IA 6.0 p.p. acima do limite (16.0% vs 10.0%).",
}


class TestDraftReviewRequest:
    def test_draft_mentions_real_client_name_and_violation_message(self):
        draft = draft_review_request("Família Teste", [_VIOLATION], "Dário Marques", "Escritório Alpha")
        assert "Família Teste" in draft["subject"]
        assert "Tema IA 6.0 p.p. acima do limite" in draft["body"]
        assert "Dário Marques" in draft["body"]
        assert "Escritório Alpha" in draft["body"]

    def test_whatsapp_text_is_shorter_and_still_mentions_the_reason(self):
        draft = draft_review_request("Família Teste", [_VIOLATION], "Dário Marques", "Escritório Alpha")
        assert len(draft["whatsapp_text"]) < len(draft["body"])
        assert "Tema IA" in draft["whatsapp_text"]

    def test_multiple_violations_all_appear_in_the_body(self):
        second = {**_VIOLATION, "type": "ABAIXO_LIQUIDEZ", "message": "Liquidez 5.0 p.p. abaixo do piso."}
        draft = draft_review_request("Família Teste", [_VIOLATION, second], "Dário Marques", "Escritório Alpha")
        assert _VIOLATION["message"] in draft["body"]
        assert second["message"] in draft["body"]

    def test_severity_wording_reflects_critical_vs_warning(self):
        critical_draft = draft_review_request("X", [_VIOLATION], "A", "O")
        warning_violation = {**_VIOLATION, "severity": "WARNING"}
        warning_draft = draft_review_request("X", [warning_violation], "A", "O")
        assert "CRÍTICA" in critical_draft["body"]
        assert "CRÍTICA" not in warning_draft["body"]


_CLIENT_WITH_BOTH = {"id": "c1", "name": "Família Teste", "email": "familia@example.com", "phone": "5511999999999"}
_CLIENT_NO_CONTACT = {"id": "c1", "name": "Família Teste", "email": None, "phone": None}
_DRAFT = draft_review_request("Família Teste", [_VIOLATION], "Dário Marques", "Escritório Alpha")


class TestSendReviewRequest:
    def test_no_contact_info_is_honest_not_an_error(self):
        results = send_review_request("office-1", _CLIENT_NO_CONTACT, _DRAFT, ["email", "whatsapp"], "user-1")
        assert results["email"]["status"] == "no_contact_info"
        assert results["whatsapp"]["status"] == "no_contact_info"

    def test_email_not_configured_is_reported_honestly(self):
        with patch("runtime.email_sender.is_configured", return_value=False):
            results = send_review_request("office-1", _CLIENT_WITH_BOTH, _DRAFT, ["email"], "user-1")
        assert results["email"]["status"] == "not_configured"

    def test_email_sent_successfully(self):
        with (
            patch("runtime.email_sender.is_configured", return_value=True),
            patch("runtime.email_sender.send_email", return_value={"to": "familia@example.com"}),
        ):
            results = send_review_request("office-1", _CLIENT_WITH_BOTH, _DRAFT, ["email"], "user-1")
        assert results["email"]["status"] == "sent"
        assert results["email"]["to"] == "familia@example.com"

    def test_email_error_is_reported_not_swallowed(self):
        from runtime.email_sender import EmailError

        with (
            patch("runtime.email_sender.is_configured", return_value=True),
            patch("runtime.email_sender.send_email", side_effect=EmailError("SMTP boom")),
        ):
            results = send_review_request("office-1", _CLIENT_WITH_BOTH, _DRAFT, ["email"], "user-1")
        assert results["email"]["status"] == "error"
        assert "SMTP boom" in results["email"]["error"]

    def test_whatsapp_not_configured_is_reported_honestly(self):
        from runtime.whatsapp import WhatsAppNotConfiguredError

        with patch("runtime.whatsapp.send_message", side_effect=WhatsAppNotConfiguredError("not set up")):
            results = send_review_request("office-1", _CLIENT_WITH_BOTH, _DRAFT, ["whatsapp"], "user-1")
        assert results["whatsapp"]["status"] == "not_configured"

    def test_whatsapp_sent_successfully(self):
        with patch("runtime.whatsapp.send_message", return_value={"key": {"id": "abc"}}):
            results = send_review_request("office-1", _CLIENT_WITH_BOTH, _DRAFT, ["whatsapp"], "user-1")
        assert results["whatsapp"]["status"] == "sent"

    def test_only_requested_channels_are_attempted(self):
        results = send_review_request("office-1", _CLIENT_NO_CONTACT, _DRAFT, ["email"], "user-1")
        assert "email" in results and "whatsapp" not in results

    def test_every_attempt_is_written_to_the_offices_own_audit_log(self, tmp_path, monkeypatch):
        import runtime.client_outreach as outreach

        monkeypatch.setattr(outreach, "_DATA_DIR", tmp_path)
        send_review_request("office-xyz", _CLIENT_NO_CONTACT, _DRAFT, ["email"], "user-1")
        audit_file = tmp_path / "outreach_audit_office-xyz.jsonl"
        assert audit_file.exists()
        assert "Família Teste" in audit_file.read_text(encoding="utf-8")


class TestOutreachHistory:
    def test_empty_when_no_audit_log_exists_yet(self, tmp_path, monkeypatch):
        import runtime.client_outreach as outreach

        monkeypatch.setattr(outreach, "_DATA_DIR", tmp_path)
        assert outreach_history("office-xyz", "c1") == []

    def test_returns_only_entries_for_the_requested_client(self, tmp_path, monkeypatch):
        import runtime.client_outreach as outreach

        monkeypatch.setattr(outreach, "_DATA_DIR", tmp_path)
        send_review_request("office-xyz", _CLIENT_NO_CONTACT, _DRAFT, ["email"], "user-1")
        other_client = {**_CLIENT_NO_CONTACT, "id": "c2", "name": "Outra Família"}
        send_review_request("office-xyz", other_client, _DRAFT, ["email"], "user-1")

        history = outreach_history("office-xyz", "c1")
        assert len(history) == 1
        assert history[0]["client_id"] == "c1"

    def test_most_recent_first(self, tmp_path, monkeypatch):
        import runtime.client_outreach as outreach

        monkeypatch.setattr(outreach, "_DATA_DIR", tmp_path)
        with patch("time.time", side_effect=[100.0]):
            send_review_request("office-xyz", _CLIENT_NO_CONTACT, _DRAFT, ["email"], "user-1")
        with patch("time.time", side_effect=[200.0]):
            send_review_request("office-xyz", _CLIENT_NO_CONTACT, _DRAFT, ["email"], "user-1")

        history = outreach_history("office-xyz", "c1")
        assert [h["timestamp"] for h in history] == [200.0, 100.0]

    def test_never_leaks_another_offices_audit_log(self, tmp_path, monkeypatch):
        import runtime.client_outreach as outreach

        monkeypatch.setattr(outreach, "_DATA_DIR", tmp_path)
        send_review_request("office-a", _CLIENT_NO_CONTACT, _DRAFT, ["email"], "user-1")
        assert outreach_history("office-b", "c1") == []
