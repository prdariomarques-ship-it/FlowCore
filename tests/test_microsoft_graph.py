"""Tests for runtime.microsoft_graph — the shared auth/token/Graph-request
provider (Sprint 17, Milestone 3), extracted from runtime/outlook.py so
runtime/calendar.py can reuse the exact same authenticated session.

msal.PublicClientApplication and requests.* are mocked throughout — no real
network or Azure AD credentials needed. This is exactly what CI exercises.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# msal/requests are requirements-api.txt (optional) — skip gracefully on a
# core-only install instead of failing (same pattern as test_api.py's
# fastapi/httpx importorskip).
msal = pytest.importorskip("msal")
requests = pytest.importorskip("requests")


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    """Never touch the real ~/.flowcore/outlook_token_cache.json in tests."""
    import runtime.microsoft_graph as mod

    monkeypatch.setattr(mod, "_CACHE_FILE", tmp_path / "outlook_token_cache.json")


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("OUTLOOK_CLIENT_ID", raising=False)
    monkeypatch.delenv("OUTLOOK_TENANT_ID", raising=False)


class TestConfig:
    def test_require_config_raises_without_client_id(self):
        from runtime.microsoft_graph import MicrosoftGraphNotConfiguredError, _require_config

        with pytest.raises(MicrosoftGraphNotConfiguredError):
            _require_config()

    def test_require_config_defaults_tenant_to_common(self, monkeypatch):
        from runtime.microsoft_graph import _require_config

        monkeypatch.setenv("OUTLOOK_CLIENT_ID", "abc123")
        client_id, tenant_id = _require_config()
        assert client_id == "abc123"
        assert tenant_id == "common"

    def test_start_device_flow_raises_without_config(self):
        from runtime.microsoft_graph import MicrosoftGraphNotConfiguredError, start_device_flow

        with pytest.raises(MicrosoftGraphNotConfiguredError):
            start_device_flow()

    def test_is_authenticated_false_without_config(self):
        from runtime.microsoft_graph import is_authenticated

        assert is_authenticated() is False

    def test_scopes_cover_mail_and_calendar(self):
        from runtime.microsoft_graph import SCOPES

        assert "Mail.Read" in SCOPES
        assert "Calendar.ReadWrite" in SCOPES


class TestDeviceFlow:
    def test_start_device_flow_success(self):
        import runtime.microsoft_graph as mod

        fake_app = MagicMock()
        fake_app.initiate_device_flow.return_value = {
            "user_code": "ABC123",
            "device_code": "xyz",
            "verification_uri": "https://microsoft.com/devicelogin",
            "expires_in": 900,
            "message": "Go to ... and enter ABC123",
        }
        with patch.object(mod, "_app", return_value=fake_app):
            flow = mod.start_device_flow()
        assert flow["user_code"] == "ABC123"
        fake_app.initiate_device_flow.assert_called_once_with(scopes=mod.SCOPES)

    def test_start_device_flow_error_response(self):
        import runtime.microsoft_graph as mod

        fake_app = MagicMock()
        fake_app.initiate_device_flow.return_value = {"error": "bad_request", "error_description": "nope"}
        with patch.object(mod, "_app", return_value=fake_app):
            with pytest.raises(mod.MicrosoftGraphError):
                mod.start_device_flow()

    def test_complete_device_flow_success(self):
        import runtime.microsoft_graph as mod

        fake_app = MagicMock()
        fake_app.acquire_token_by_device_flow.return_value = {"access_token": "tok"}
        with patch.object(mod, "_app", return_value=fake_app):
            mod.complete_device_flow({"device_code": "xyz"})  # should not raise

    def test_complete_device_flow_failure(self):
        import runtime.microsoft_graph as mod

        fake_app = MagicMock()
        fake_app.acquire_token_by_device_flow.return_value = {"error_description": "expired_token"}
        with patch.object(mod, "_app", return_value=fake_app):
            with pytest.raises(mod.MicrosoftGraphError, match="expired_token"):
                mod.complete_device_flow({"device_code": "xyz"})


class TestAuthState:
    def test_is_authenticated_no_accounts(self):
        import runtime.microsoft_graph as mod

        fake_app = MagicMock()
        fake_app.get_accounts.return_value = []
        with patch.object(mod, "_app", return_value=fake_app):
            assert mod.is_authenticated() is False

    def test_is_authenticated_silent_success(self):
        import runtime.microsoft_graph as mod

        fake_app = MagicMock()
        fake_app.get_accounts.return_value = [{"username": "me@example.com"}]
        fake_app.acquire_token_silent.return_value = {"access_token": "tok"}
        with patch.object(mod, "_app", return_value=fake_app):
            assert mod.is_authenticated() is True

    def test_is_authenticated_silent_fails(self):
        import runtime.microsoft_graph as mod

        fake_app = MagicMock()
        fake_app.get_accounts.return_value = [{"username": "me@example.com"}]
        fake_app.acquire_token_silent.return_value = None
        with patch.object(mod, "_app", return_value=fake_app):
            assert mod.is_authenticated() is False

    def test_access_token_raises_without_accounts(self):
        import runtime.microsoft_graph as mod

        fake_app = MagicMock()
        fake_app.get_accounts.return_value = []
        with patch.object(mod, "_app", return_value=fake_app):
            with pytest.raises(mod.MicrosoftGraphAuthRequiredError):
                mod._access_token()

    def test_access_token_raises_when_silent_fails(self):
        import runtime.microsoft_graph as mod

        fake_app = MagicMock()
        fake_app.get_accounts.return_value = [{"username": "me@example.com"}]
        fake_app.acquire_token_silent.return_value = None
        with patch.object(mod, "_app", return_value=fake_app):
            with pytest.raises(mod.MicrosoftGraphAuthRequiredError):
                mod._access_token()

    def test_access_token_returns_token(self):
        import runtime.microsoft_graph as mod

        fake_app = MagicMock()
        fake_app.get_accounts.return_value = [{"username": "me@example.com"}]
        fake_app.acquire_token_silent.return_value = {"access_token": "real-token"}
        with patch.object(mod, "_app", return_value=fake_app):
            assert mod._access_token() == "real-token"


class TestGraphVerbs:
    def _mock_response(self, status_code=200, json_data=None, text=None):
        r = MagicMock()
        r.status_code = status_code
        r.json.return_value = json_data if json_data is not None else {}
        # A real Response's .text reflects the body — mirror that here so
        # _handle_response's `if r.text` guard behaves like it would for real.
        r.text = text if text is not None else ("{}" if json_data is None else str(json_data))
        return r

    def test_graph_get_success(self):
        import runtime.microsoft_graph as mod

        with (
            patch.object(mod, "_access_token", return_value="tok"),
            patch("runtime.microsoft_graph.requests.get", return_value=self._mock_response(json_data={"a": 1})) as m,
        ):
            result = mod.graph_get("/me/messages", {"$top": "5"})
        assert result == {"a": 1}
        args, kwargs = m.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer tok"
        assert kwargs["params"]["$top"] == "5"

    def test_graph_get_raises_on_non_200(self):
        import runtime.microsoft_graph as mod

        with (
            patch.object(mod, "_access_token", return_value="tok"),
            patch(
                "runtime.microsoft_graph.requests.get",
                return_value=self._mock_response(status_code=403, text="Forbidden"),
            ),
        ):
            with pytest.raises(mod.MicrosoftGraphError, match="403"):
                mod.graph_get("/me/messages")

    def test_graph_get_raises_without_authentication(self):
        import runtime.microsoft_graph as mod

        with patch.object(mod, "_access_token", side_effect=mod.MicrosoftGraphAuthRequiredError("not authed")):
            with pytest.raises(mod.MicrosoftGraphAuthRequiredError):
                mod.graph_get("/me/messages")

    def test_graph_post_success(self):
        import runtime.microsoft_graph as mod

        with (
            patch.object(mod, "_access_token", return_value="tok"),
            patch(
                "runtime.microsoft_graph.requests.post",
                return_value=self._mock_response(status_code=201, json_data={"id": "new-event"}),
            ) as m,
        ):
            result = mod.graph_post("/me/events", {"subject": "Hi"})
        assert result == {"id": "new-event"}
        args, kwargs = m.call_args
        assert kwargs["json"] == {"subject": "Hi"}

    def test_graph_patch_success(self):
        import runtime.microsoft_graph as mod

        with (
            patch.object(mod, "_access_token", return_value="tok"),
            patch(
                "runtime.microsoft_graph.requests.patch",
                return_value=self._mock_response(json_data={"id": "e1", "subject": "Updated"}),
            ),
        ):
            result = mod.graph_patch("/me/events/e1", {"subject": "Updated"})
        assert result["subject"] == "Updated"

    def test_graph_delete_success(self):
        import runtime.microsoft_graph as mod

        with (
            patch.object(mod, "_access_token", return_value="tok"),
            patch(
                "runtime.microsoft_graph.requests.delete",
                return_value=self._mock_response(status_code=204, text=""),
            ) as m,
        ):
            mod.graph_delete("/me/events/e1")  # should not raise
        m.assert_called_once()

    def test_graph_delete_raises_on_failure(self):
        import runtime.microsoft_graph as mod

        with (
            patch.object(mod, "_access_token", return_value="tok"),
            patch(
                "runtime.microsoft_graph.requests.delete",
                return_value=self._mock_response(status_code=404, text="Not found"),
            ),
        ):
            with pytest.raises(mod.MicrosoftGraphError, match="404"):
                mod.graph_delete("/me/events/e1")
