"""FlowCore Dashboard v4 routes.

Implements all endpoints consumed by the Web Dashboard v4:
  - /api/ask              — agent chat (Ollama-first, graceful fallback)
  - /api/ai-runtime/*     — Ollama model management
  - /api/market/*         — market data [STUB — populated by market engine]
  - /api/macro-score/*    — macro scoring [STUB]
  - /api/regime/signals   — SCPX regime [STUB]
  - /api/portfolios/*     — portfolio analytics [STUB]
  - /api/assets/{symbol}  — asset details [STUB]
  - /api/outlook/*        — Outlook / email integration [STUB]
  - /api/calendar/*       — calendar integration [STUB]

Endpoints marked [STUB] return empty but correctly-shaped JSON so the
dashboard never crashes on first deploy. Replace stub bodies with real
domain module calls as each integration is rolled out.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Query
from pydantic import BaseModel

_OLLAMA_BASE = "http://localhost:11434"
_DATA_DIR = Path.home() / ".flowcore"


# ── Request schemas (module-level so FastAPI resolves them correctly) ──────────

class AskRequest(BaseModel):
    question: str
    model: str = ""
    history: list[dict] = []


class ModelAction(BaseModel):
    model: str
    keep_alive: str = "5m"


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _ollama(method: str, path: str, body: dict | None = None, timeout: int = 30) -> dict:
    """Call the local Ollama HTTP API; raises RuntimeError if unavailable."""
    import urllib.error
    import urllib.request

    url = f"{_OLLAMA_BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama unavailable: {exc}") from exc


def _read_json(filename: str, default: Any = None) -> Any:
    p = _DATA_DIR / filename
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


# ── Registration ───────────────────────────────────────────────────────────────

def register_dashboard_routes(app, version: str) -> None:
    """Register all Dashboard v4 API routes onto *app*."""

    # ── Agent chat (/api/ask) ──────────────────────────────────────────────────

    @app.post("/api/ask")
    async def ask(data: AskRequest):
        if not data.question.strip():
            raise HTTPException(status_code=422, detail="question is required")

        # Try FlowCore AgentRunner (ask agent) first
        try:
            from agents.runner import AgentRunner
            runner = AgentRunner(require_passport=False)
            agents = {a["name"] for a in runner.list_agents()}
            if "ask" in agents:
                record = await runner.run(
                    "ask",
                    {"question": data.question, "history": data.history},
                    passport_agent_name="dashboard",
                )
                if record.status == "completed" and record.result:
                    return {"answer": record.result, "provider": "flowcore-agent", "model": ""}
        except Exception:
            pass

        # Ollama fallback
        cfg = _read_json("ai.json", {})
        model = data.model or cfg.get("model", "llama3")
        messages = data.history + [{"role": "user", "content": data.question}]
        try:
            resp = _ollama("POST", "/api/chat", {
                "model": model,
                "messages": messages,
                "stream": False,
            }, timeout=90)
            answer = resp.get("message", {}).get("content", "")
            return {"answer": answer, "provider": "ollama", "model": model}
        except RuntimeError as exc:
            return {
                "answer": "Ollama não está em execução neste servidor. Inicie-o com `ollama serve`.",
                "provider": "unavailable",
                "model": model,
                "error": str(exc),
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    # ── AI runtime / Ollama model management ─────────────────────────────────

    @app.get("/api/ai-runtime/models")
    async def ai_models():
        try:
            resp = _ollama("GET", "/api/tags")
            models = [
                {
                    "name": m.get("name", ""),
                    "size_bytes": m.get("size", 0),
                    "modified_at": m.get("modified_at", ""),
                    "loaded": False,
                }
                for m in resp.get("models", [])
            ]
            return {"models": models, "provider": "ollama"}
        except RuntimeError:
            return {"models": [], "provider": "unavailable"}

    @app.get("/api/ai-runtime/memory")
    async def ai_memory():
        try:
            resp = _ollama("GET", "/api/ps")
            loaded = [
                {
                    "name": m.get("name", ""),
                    "size_vram": m.get("size_vram", 0),
                    "expires_at": m.get("expires_at", ""),
                }
                for m in resp.get("models", [])
            ]
            context_window = loaded[0]["size_vram"] if loaded else 0
            return {
                "loaded_models": loaded,
                "provider": "ollama",
                "context_window": context_window,
            }
        except RuntimeError:
            return {"loaded_models": [], "provider": "unavailable", "context_window": 0}

    @app.post("/api/ai-runtime/load")
    async def ai_load(data: ModelAction):
        try:
            _ollama("POST", "/api/generate", {
                "model": data.model,
                "prompt": "",
                "keep_alive": data.keep_alive,
                "stream": False,
            }, timeout=120)
            return {"loaded": True, "model": data.model}
        except RuntimeError as exc:
            return {"loaded": False, "model": data.model, "error": str(exc)}

    @app.post("/api/ai-runtime/unload")
    async def ai_unload(data: ModelAction):
        try:
            _ollama("POST", "/api/generate", {
                "model": data.model,
                "prompt": "",
                "keep_alive": 0,
                "stream": False,
            }, timeout=30)
            return {"unloaded": True, "model": data.model}
        except RuntimeError as exc:
            return {"unloaded": False, "model": data.model, "error": str(exc)}

    # ── Market data [STUB] ────────────────────────────────────────────────────

    @app.get("/api/market/fx")
    async def market_fx():
        return {
            "pairs": [],
            "usd_regime": "neutral",
            "updated_at": time.time(),
            "stub": True,
        }

    @app.get("/api/market/yield-curve")
    async def market_yield_curve():
        return {
            "points": [],
            "slope_10y_2y_bps": None,
            "shape": "unknown",
            "interpretation": "",
            "updated_at": time.time(),
            "stub": True,
        }

    @app.get("/api/market/rebalancing")
    async def market_rebalancing():
        return {"actions": [], "updated_at": time.time(), "stub": True}

    @app.get("/api/market/watchlists")
    async def market_watchlists():
        return {"watchlists": [], "updated_at": time.time(), "stub": True}

    @app.get("/api/market/alerts")
    async def market_alerts():
        return {"alerts": [], "updated_at": time.time(), "stub": True}

    @app.get("/api/market/calendar")
    async def market_economic_calendar():
        return {"events": [], "updated_at": time.time(), "stub": True}

    @app.get("/api/market/news")
    async def market_news():
        return {"groups": [], "updated_at": time.time(), "stub": True}

    # ── Macro score [STUB] ────────────────────────────────────────────────────

    @app.get("/api/macro-score/current")
    async def macro_score_current():
        return {
            "score": None,
            "dimensions": {},
            "updated_at": time.time(),
            "stub": True,
        }

    @app.get("/api/macro-score/history")
    async def macro_score_history(
        periods: str = Query("D-1,D-5,D-20,D-60"),
    ):
        return {"history": [], "periods": periods, "updated_at": time.time(), "stub": True}

    # ── Regime signals [STUB] ─────────────────────────────────────────────────

    @app.get("/api/regime/signals")
    async def regime_signals():
        return {
            "regime": "neutral",
            "label": "Neutro",
            "signals": [],
            "updated_at": time.time(),
            "stub": True,
        }

    # ── Portfolios [STUB + file-backed list] ──────────────────────────────────

    @app.get("/api/portfolios")
    async def list_portfolios():
        data = _read_json("portfolios.json", [])
        return data if isinstance(data, list) else []

    @app.get("/api/portfolios/{portfolio_id}")
    async def get_portfolio(portfolio_id: str):
        portfolios = _read_json("portfolios.json", [])
        for p in (portfolios if isinstance(portfolios, list) else []):
            if p.get("id") == portfolio_id:
                return p
        raise HTTPException(status_code=404, detail="Portfolio not found")

    @app.get("/api/portfolios/{portfolio_id}/summary")
    async def portfolio_summary(portfolio_id: str):
        return {
            "portfolio_id": portfolio_id,
            "positions": [],
            "total_value": 0,
            "currency": "BRL",
            "stub": True,
        }

    @app.get("/api/portfolios/{portfolio_id}/exposure")
    async def portfolio_exposure(portfolio_id: str):
        return {
            "portfolio_id": portfolio_id,
            "by_asset_class": [],
            "by_sector": [],
            "by_industry": [],
            "by_country": [],
            "by_currency": [],
            "stub": True,
        }

    @app.get("/api/portfolios/{portfolio_id}/impact")
    async def portfolio_impact(portfolio_id: str):
        return {"portfolio_id": portfolio_id, "impact": [], "stub": True}

    @app.get("/api/portfolios/{portfolio_id}/decision")
    async def portfolio_decision(portfolio_id: str):
        return {
            "portfolio_id": portfolio_id,
            "decisions": [],
            "readiness_score": None,
            "sub_scores": {},
            "top_risks": [],
            "top_opportunities": [],
            "stub": True,
        }

    @app.get("/api/portfolios/{portfolio_id}/narrative")
    async def portfolio_narrative(portfolio_id: str):
        return {
            "portfolio_id": portfolio_id,
            "narrative": "Portfolio analytics module not configured on this instance.",
            "stub": True,
        }

    # ── Assets [STUB] ─────────────────────────────────────────────────────────

    @app.get("/api/assets/{symbol}")
    async def get_asset(symbol: str):
        return {
            "symbol": symbol.upper(),
            "name": None,
            "theme": None,
            "region": None,
            "income": None,
            "inflation_protection": None,
            "stub": True,
        }

    # ── Outlook / email [STUB] ────────────────────────────────────────────────

    @app.get("/api/outlook/auth/status")
    async def outlook_auth_status():
        cfg = _read_json("outlook.json", {})
        return {
            "authenticated": cfg.get("authenticated", False),
            "email": cfg.get("email"),
            "expires_at": cfg.get("expires_at"),
        }

    @app.get("/api/outlook/auth/start")
    async def outlook_auth_start():
        return {
            "auth_url": None,
            "message": "Outlook OAuth not configured on this instance.",
            "stub": True,
        }

    @app.get("/api/outlook/inbox")
    async def outlook_inbox(limit: int = Query(20, le=100)):
        return {"messages": [], "unread": 0, "stub": True}

    @app.get("/api/outlook/search")
    async def outlook_search(q: str = Query(..., min_length=1)):
        return {"query": q, "messages": [], "stub": True}

    # ── Calendar [STUB] ───────────────────────────────────────────────────────

    @app.get("/api/calendar/today")
    async def calendar_today():
        return {
            "events": [],
            "date": time.strftime("%Y-%m-%d"),
            "stub": True,
        }

    @app.get("/api/calendar/week")
    async def calendar_week():
        return {"events": [], "stub": True}

    @app.get("/api/calendar/next")
    async def calendar_next():
        return {"event": None, "stub": True}

    @app.get("/api/calendar/search")
    async def calendar_search(q: str = Query(..., min_length=1)):
        return {"query": q, "events": [], "stub": True}
