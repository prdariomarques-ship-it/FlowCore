"""Tests for runtime.whatsapp — WhatsApp via Evolution API (Sprint 17, Milestone 4).

requests is mocked throughout — no real network/Evolution API calls. This is
exactly what CI exercises (it never has a real Evolution API instance).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# requests is requirements-api.txt (optional) — skip gracefully on a
# core-only install instead of failing (same pattern as test_outlook.py).
requests = pytest.importorskip("requests")


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("EVOLUTION_API_URL", raising=False)
    monkeypatch.delenv("EVOLUTION_API_KEY", raising=False)
    monkeypatch.delenv("EVOLUTION_INSTANCE_NAME", raising=False)


def _mock_response(status_code=200, json_data=None, text=""):
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = json_data if json_data is not None else {}
    r.text = text
    return r


class TestConfig:
    def test_api_url_defaults_to_local(self):
        from runtime.whatsapp import _api_url

        assert _api_url() == "http://127.0.0.1:8080"

    def test_api_url_respects_env_override(self, monkeypatch):
        from runtime.whatsapp import _api_url

        monkeypatch.setenv("EVOLUTION_API_URL", "http://example.com:9000/")
        assert _api_url() == "http://example.com:9000"

    def test_require_config_raises_without_api_key(self):
        from runtime.whatsapp import WhatsAppNotConfiguredError, _require_config

        with pytest.raises(WhatsAppNotConfiguredError):
            _require_config()

    def test_require_config_raises_without_instance_name(self, monkeypatch):
        from runtime.whatsapp import WhatsAppNotConfiguredError, _require_config

        monkeypatch.setenv("EVOLUTION_API_KEY", "key123")
        with pytest.raises(WhatsAppNotConfiguredError):
            _require_config()

    def test_require_config_succeeds_with_both_set(self, monkeypatch):
        from runtime.whatsapp import _require_config

        monkeypatch.setenv("EVOLUTION_API_KEY", "key123")
        monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "my-instance")
        api_key, instance = _require_config()
        assert api_key == "key123"
        assert instance == "my-instance"

    def test_status_raises_without_config(self):
        from runtime.whatsapp import WhatsAppNotConfiguredError, get_status

        with pytest.raises(WhatsAppNotConfiguredError):
            get_status()

    def test_send_raises_without_config(self):
        from runtime.whatsapp import WhatsAppNotConfiguredError, send_message

        with pytest.raises(WhatsAppNotConfiguredError):
            send_message("5511999999999", "hi")


class TestHealth:
    def test_health_does_not_require_config(self):
        # No EVOLUTION_API_KEY/EVOLUTION_INSTANCE_NAME set (see _clear_env) —
        # health must still work, it only checks server reachability.
        import runtime.whatsapp as mod

        payload = {"status": 200, "message": "Welcome", "version": "2.2.3"}
        with patch("runtime.whatsapp.requests.get", return_value=_mock_response(json_data=payload)) as m:
            result = mod.check_health()
        assert result == payload
        assert m.call_args[0][0] == "http://127.0.0.1:8080/"

    def test_health_raises_on_non_200(self):
        import runtime.whatsapp as mod

        with patch("runtime.whatsapp.requests.get", return_value=_mock_response(status_code=500, text="oops")):
            with pytest.raises(mod.WhatsAppError, match="500"):
                mod.check_health()

    def test_health_raises_on_connection_error(self):
        import runtime.whatsapp as mod

        with patch("runtime.whatsapp.requests.get", side_effect=requests.RequestException("refused")):
            with pytest.raises(mod.WhatsAppError, match="unreachable"):
                mod.check_health()


class TestStatus:
    def test_status_success(self, monkeypatch):
        import runtime.whatsapp as mod

        monkeypatch.setenv("EVOLUTION_API_KEY", "key123")
        monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "my-instance")
        payload = {"instance": {"instanceName": "my-instance", "state": "open"}}
        with patch("runtime.whatsapp.requests.get", return_value=_mock_response(json_data=payload)) as m:
            result = mod.get_status()
        assert result == payload
        assert "my-instance" in m.call_args[0][0]
        assert m.call_args[1]["headers"]["apikey"] == "key123"

    def test_status_raises_on_error(self, monkeypatch):
        import runtime.whatsapp as mod

        monkeypatch.setenv("EVOLUTION_API_KEY", "key123")
        monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "my-instance")
        with patch("runtime.whatsapp.requests.get", return_value=_mock_response(status_code=401, text="bad key")):
            with pytest.raises(mod.WhatsAppError, match="401"):
                mod.get_status()


class TestSendMessage:
    def test_send_success(self, monkeypatch):
        import runtime.whatsapp as mod

        monkeypatch.setenv("EVOLUTION_API_KEY", "key123")
        monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "my-instance")
        payload = {"key": {"id": "ABC"}, "status": "PENDING"}
        with patch("runtime.whatsapp.requests.post", return_value=_mock_response(json_data=payload)) as m:
            result = mod.send_message("5511999999999", "hello")
        assert result == payload
        assert "my-instance" in m.call_args[0][0]
        assert m.call_args[1]["json"] == {"number": "5511999999999", "text": "hello"}
        assert m.call_args[1]["headers"]["apikey"] == "key123"

    def test_send_raises_on_error(self, monkeypatch):
        import runtime.whatsapp as mod

        monkeypatch.setenv("EVOLUTION_API_KEY", "key123")
        monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "my-instance")
        with patch("runtime.whatsapp.requests.post", return_value=_mock_response(status_code=400, text="bad number")):
            with pytest.raises(mod.WhatsAppError, match="400"):
                mod.send_message("invalid", "hello")

    def test_send_raises_on_connection_error(self, monkeypatch):
        import runtime.whatsapp as mod

        monkeypatch.setenv("EVOLUTION_API_KEY", "key123")
        monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "my-instance")
        with patch("runtime.whatsapp.requests.post", side_effect=requests.RequestException("timeout")):
            with pytest.raises(mod.WhatsAppError):
                mod.send_message("5511999999999", "hello")
