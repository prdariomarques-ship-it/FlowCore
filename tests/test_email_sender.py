"""Tests for runtime/email_sender.py — plain SMTP outbound email."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    path = tmp_path / "email.json"
    import runtime.email_sender as email_sender

    monkeypatch.setattr(email_sender, "_CONFIG_PATH", path)
    return path


class TestConfiguration:
    def test_is_configured_false_when_no_file(self, config_path):
        from runtime.email_sender import is_configured

        assert is_configured() is False

    def test_is_configured_false_when_missing_required_field(self, config_path):
        config_path.write_text(json.dumps({"smtp_host": "smtp.example.com"}))
        from runtime.email_sender import is_configured

        assert is_configured() is False

    def test_is_configured_true_with_full_config(self, config_path):
        config_path.write_text(json.dumps({
            "smtp_host": "smtp.example.com", "smtp_port": 587,
            "username": "a@example.com", "password": "app-password", "from_address": "a@example.com",
        }))
        from runtime.email_sender import is_configured

        assert is_configured() is True


class TestSendEmail:
    def test_raises_when_not_configured(self, config_path):
        from runtime.email_sender import EmailNotConfiguredError, send_email

        with pytest.raises(EmailNotConfiguredError):
            send_email("client@example.com", "Assunto", "Corpo")

    def test_sends_via_smtp_when_configured(self, config_path):
        config_path.write_text(json.dumps({
            "smtp_host": "smtp.example.com", "smtp_port": 587,
            "username": "a@example.com", "password": "app-password",
            "from_address": "a@example.com", "from_name": "FlowCore",
        }))
        from runtime.email_sender import send_email

        mock_server = MagicMock()
        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.return_value.__enter__.return_value = mock_server
            result = send_email("client@example.com", "Revisão de carteira", "Olá!")

        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("a@example.com", "app-password")
        mock_server.sendmail.assert_called_once()
        assert result["to"] == "client@example.com"

    def test_smtp_failure_raises_email_error(self, config_path):
        import smtplib

        config_path.write_text(json.dumps({
            "smtp_host": "smtp.example.com", "smtp_port": 587,
            "username": "a@example.com", "password": "app-password", "from_address": "a@example.com",
        }))
        from runtime.email_sender import EmailError, send_email

        with patch("smtplib.SMTP", side_effect=smtplib.SMTPConnectError(421, "boom")):
            with pytest.raises(EmailError):
                send_email("client@example.com", "Assunto", "Corpo")
