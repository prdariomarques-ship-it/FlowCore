"""Tests for api/tenant_auth.py — get_current_user/require_role."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import HTTPException  # noqa: E402

from api.tenant_auth import get_current_user, require_role  # noqa: E402


class _FakeRequest:
    def __init__(self, headers: dict[str, str]):
        self.headers = headers


class TestGetCurrentUser:
    def test_missing_header_is_401(self):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_current_user(_FakeRequest({})))
        assert exc.value.status_code == 401

    def test_malformed_header_is_401(self):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_current_user(_FakeRequest({"Authorization": "not-bearer xyz"})))
        assert exc.value.status_code == 401

    def test_invalid_token_is_401(self):
        with patch("storage.tenant_repo.TenantRepository.get_session_user", return_value=None):
            with pytest.raises(HTTPException) as exc:
                asyncio.run(get_current_user(_FakeRequest({"Authorization": "Bearer bogus"})))
        assert exc.value.status_code == 401

    def test_valid_token_returns_user(self):
        fake_user = {"id": "u1", "office_id": "o1", "email": "a@b.com", "name": "A", "role": "owner", "created_at": 0}

        async def fake_get_session_user(self, token):
            assert token == "good-token"
            return fake_user

        with patch("storage.tenant_repo.TenantRepository.get_session_user", fake_get_session_user):
            user = asyncio.run(get_current_user(_FakeRequest({"Authorization": "Bearer good-token"})))
        assert user == fake_user


class TestRequireRole:
    def test_allowed_role_passes(self):
        require_role({"role": "owner"}, "owner", "manager")  # no raise

    def test_disallowed_role_is_403(self):
        with pytest.raises(HTTPException) as exc:
            require_role({"role": "assistant"}, "owner", "manager")
        assert exc.value.status_code == 403
