"""API token validation for endpoints exposed beyond 127.0.0.1.

FlowCore's FastAPI API binds to 127.0.0.1 by default and is intentionally
unauthenticated for local use. Endpoints reachable from the LAN/mobile
(Caddy reverse proxy on 192.168.1.66/flowcore/, /api/mercado/*, AI Runtime,
Telegram briefing, etc.) validate the shared API token via the
``X-FlowCore-Token`` header -- exactly the same credential the Caddy
frontend proxy already proves it holds (the .env docstring states:
"FLOWCORE_API_TOKEN: obrigatorio quando api.host != 127.0.0.1").

Usage inside the router:

    from api.auth import require_api_token

    @app.get("/api/ai-runtime/health")
    async def ai_runtime_health():
        require_api_token(Request)  # raises HTTPException 401 if invalid
        ...
"""
from __future__ import annotations

import os
from fastapi import HTTPException, Request

__all__ = ["require_api_token", "get_api_token"]

_TOKEN_HEADER = "X-FlowCore-Token"


def get_api_token() -> str | None:
    """The configured token, preferring the env var over config (they are
    kept in sync by deployment, but the env is the single source of truth
    after a `.env`-only reload without touching config/local.json)."""
    env = os.environ.get("FLOWCORE_API_TOKEN")
    if env:
        return env
    try:
        from config.loader import get_config

        cfg = get_config()
        token = cfg.get("api", {}).get("token") or cfg.get("api_token")
        return str(token) if token else None
    except Exception:
        return None


def require_api_token(request: Request) -> None:
    """Raise 401 when a token is configured but missing/invalid on the
    request. If no token is configured at all, the check is a no-op --
    matching the deploy doc's "required when api.host != 127.0.0.1" rule:
    local-only deployments keep working untouched."""
    configured = get_api_token()
    if not configured:
        return
    provided = request.headers.get(_TOKEN_HEADER) or request.query_params.get("token")
    if not provided or provided != configured:
        raise HTTPException(status_code=401, detail="invalid or missing X-FlowCore-Token")
