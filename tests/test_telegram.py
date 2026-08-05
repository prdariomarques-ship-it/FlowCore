"""Tests for runtime.telegram — Telegram integration (Sprint 17, Milestone 4).

Stdlib-only (urllib) — no requirements-api.txt dependency, so unlike
test_outlook.py/test_whatsapp.py this file needs no pytest.importorskip
guard; it runs on the core tier too.

urllib.request.urlopen is mocked throughout — no real network/bot calls.
"""

from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)


def _mock_urlopen(payload: dict):
    cm = MagicMock()
    cm.__enter__.return_value.read.return_value = json.dumps(payload).encode("utf-8")
    return cm


class TestConfiguration:
    def test_neither_set(self):
        from runtime.telegram import get_configuration

        result = get_configuration()
        assert result == {"configured": False, "token_set": False, "chat_id_set": False}

    def test_only_token_set(self, monkeypatch):
        from runtime.telegram import get_configuration

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        result = get_configuration()
        assert result == {"configured": False, "token_set": True, "chat_id_set": False}

    def test_both_set(self, monkeypatch):
        from runtime.telegram import get_configuration

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
        result = get_configuration()
        assert result == {"configured": True, "token_set": True, "chat_id_set": True}


class TestHealth:
    def test_raises_without_token(self):
        from runtime.telegram import TelegramNotConfiguredError, check_health

        with pytest.raises(TelegramNotConfiguredError):
            check_health()

    def test_success(self, monkeypatch):
        from runtime.telegram import check_health

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        payload = {"ok": True, "result": {"id": 123, "username": "spcx_monitor_bot"}}
        with patch("runtime.telegram.urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            result = check_health()
        assert result["username"] == "spcx_monitor_bot"

    def test_api_returns_ok_false(self, monkeypatch):
        from runtime.telegram import TelegramError, check_health

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bad-token")
        payload = {"ok": False, "description": "Unauthorized"}
        with patch("runtime.telegram.urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            with pytest.raises(TelegramError):
                check_health()

    def test_http_error(self, monkeypatch):
        from runtime.telegram import TelegramError, check_health

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        err = urllib.error.HTTPError("url", 401, "Unauthorized", {}, MagicMock())
        err.read = lambda: b'{"description": "Unauthorized"}'
        with patch("runtime.telegram.urllib.request.urlopen", side_effect=err):
            with pytest.raises(TelegramError, match="401"):
                check_health()

    def test_connection_error(self, monkeypatch):
        from runtime.telegram import TelegramError, check_health

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        with patch("runtime.telegram.urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            with pytest.raises(TelegramError, match="unreachable"):
                check_health()


class TestSendMessage:
    def test_raises_without_token(self):
        from runtime.telegram import TelegramNotConfiguredError, send_message

        with pytest.raises(TelegramNotConfiguredError):
            send_message("hi")

    def test_raises_without_chat_id(self, monkeypatch):
        from runtime.telegram import TelegramNotConfiguredError, send_message

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        with pytest.raises(TelegramNotConfiguredError):
            send_message("hi")

    def test_success_with_env_chat_id(self, monkeypatch):
        from runtime.telegram import send_message

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "883232211")
        payload = {"ok": True, "result": {"message_id": 42}}
        with patch("runtime.telegram.urllib.request.urlopen", return_value=_mock_urlopen(payload)) as m:
            result = send_message("hello")
        assert result["message_id"] == 42
        req = m.call_args[0][0]
        body = json.loads(req.data.decode("utf-8"))
        assert body == {"chat_id": "883232211", "text": "hello"}

    def test_explicit_chat_id_overrides_env(self, monkeypatch):
        from runtime.telegram import send_message

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "883232211")
        payload = {"ok": True, "result": {"message_id": 43}}
        with patch("runtime.telegram.urllib.request.urlopen", return_value=_mock_urlopen(payload)) as m:
            send_message("hello", chat_id="999")
        req = m.call_args[0][0]
        body = json.loads(req.data.decode("utf-8"))
        assert body["chat_id"] == "999"

    def test_explicit_chat_id_without_env(self, monkeypatch):
        from runtime.telegram import send_message

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        payload = {"ok": True, "result": {"message_id": 44}}
        with patch("runtime.telegram.urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            result = send_message("hello", chat_id="999")
        assert result["message_id"] == 44

    def test_api_error(self, monkeypatch):
        from runtime.telegram import TelegramError, send_message

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "883232211")
        payload = {"ok": False, "description": "chat not found"}
        with patch("runtime.telegram.urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            with pytest.raises(TelegramError):
                send_message("hello")
