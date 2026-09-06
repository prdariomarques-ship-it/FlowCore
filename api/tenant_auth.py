"""Per-request identity for the multi-office FlowCore API.

Distinct from api/auth.py's `require_api_token`: that's a single
device-wide shared secret (the "Personal Execution OS" model — one user,
one token). This module is the multi-tenant login layer added on top of
it — a real user, belonging to a real office, identified by a bearer
session token from storage/tenant_repo.py. The two are complementary,
not alternatives: a LAN/mobile deployment can still require the device
token AND a logged-in user.

Usage inside a route handler (this codebase has no established
`Depends()` convention — see api/auth.py's require_api_token for the
same manual-call style):

    from api.tenant_auth import get_current_user, require_role

    @app.get("/api/alerts")
    async def alerts(request: Request):
        user = await get_current_user(request)
        ...
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

__all__ = ["get_current_user", "require_role"]

_AUTH_HEADER = "Authorization"
_BEARER_PREFIX = "Bearer "


def _extract_token(request: Request) -> str | None:
    header = request.headers.get(_AUTH_HEADER)
    if header and header.startswith(_BEARER_PREFIX):
        return header[len(_BEARER_PREFIX):].strip()
    return None


async def get_current_user(request: Request) -> dict[str, Any]:
    """Resolve the bearer token on `request` to a user, or raise 401.

    Returns the same public user shape as TenantRepository:
    {id, office_id, email, name, role, created_at}. Every wealth-
    management route that touches office-scoped data must call this and
    use the returned `office_id` to scope its query — never a global
    default — so one office can never see another's data.
    """
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")

    from storage.tenant_repo import TenantRepository

    user = await TenantRepository().get_session_user(token)
    if not user:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    return user


def require_role(user: dict[str, Any], *allowed_roles: str) -> None:
    """Raise 403 unless `user["role"]` is one of `allowed_roles`."""
    if user["role"] not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail=f"role '{user['role']}' cannot perform this action (requires one of {list(allowed_roles)})",
        )
