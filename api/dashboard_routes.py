"""FlowCore Dashboard v4 routes.

Implements all endpoints consumed by the Web Dashboard v4:
  - /api/ask              — agent chat (OpenAI → Ollama fallback chain)
  - /api/ai-runtime/*     — AI model management
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

AI provider configuration  (~/.flowcore/ai.json)
-------------------------------------------------
Two provider slots — the first that is configured and reachable wins.

OpenAI-compatible (e.g. Hermes Agent / LM Studio / Jan):
    {
        "openai_url":   "http://192.168.x.y:PORT",
        "openai_model": "nemotron-3.5-lightning"
    }

Ollama (local or remote via Tailscale):
    {
        "ollama_url": "http://100.x.y.z:11434",
        "model":      "qwen3:4b"
    }

All values are read at request time — no restart needed after editing.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Query
from pydantic import BaseModel

_OLLAMA_DEFAULT = "http://localhost:11434"
_DATA_DIR = Path.home() / ".flowcore"
_REFERENCE_PORTFOLIO = Path(__file__).resolve().parents[1] / "config" / "portfolio_moderate_1m.json"


def _load_reference_portfolio() -> dict[str, Any]:
    """Load the bundled reference portfolio without requiring live market data."""
    runtime_copy = _DATA_DIR / "portfolio_moderate_1m.json"
    for path in (runtime_copy, _REFERENCE_PORTFOLIO):
        try:
            if path.exists():
                data = json.loads(path.read_text())
                if isinstance(data, dict):
                    return data
        except (OSError, json.JSONDecodeError):
            continue
    return {"id": "moderate-ia-1m", "name": "Carteira Moderada — R$ 1 milhão", "reference_value": 1000000, "target_allocation": []}


def _review_reference_portfolio(portfolio: dict[str, Any], events: list[str] | None = None, current: dict[str, float] | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    allocation = portfolio.get("target_allocation", [])
    events = events or []
    current = current or {}
    policy = portfolio.get("review_policy", {})
    threshold = float(policy.get("rebalance_trigger_absolute_points", 3.0))
    drift = []
    alerts = []
    for item in allocation:
        target = float(item.get("weight", 0))
        actual = float(current.get(item.get("id", ""), target if not current else 0))
        points = round(actual - target, 2)
        drift.append({"id": item.get("id"), "target_weight": target, "current_weight": actual, "drift_points": points, "outside_band": abs(points) >= threshold})
        if current and abs(points) >= threshold:
            alerts.append(f"Desvio de {points:+.2f} p.p. em {item.get('label', item.get('id'))}")
    if not current:
        alerts.extend(["Carteira de referência sem posições reais informadas", "Revisão de mercado ao vivo depende de uma fonte de dados configurada"])
    if events:
        alerts.extend([f"Evento recebido: {event}" for event in events])
    return {
        "portfolio_id": portfolio.get("id", "moderate-ia-1m"), "reviewed_at": now,
        "mode": "review_and_alert_only", "live_data": bool(events), "orders_executed": False,
        "status": "alert" if alerts and (events or current) else "reference_only",
        "alerts": alerts, "events_received": events, "drift": drift,
        "next_action": "Avaliar proposta e exigir aprovação humana antes de qualquer ordem" if alerts and (events or current) else "Configurar posições e fonte de dados antes de qualquer rebalanceamento",
    }


# ── Request schemas (module-level so FastAPI resolves them correctly) ──────────

class AskRequest(BaseModel):
    question: str
    model: str = ""
    history: list[dict] = []


class ModelAction(BaseModel):
    model: str
    keep_alive: str = "5m"


class AIConfig(BaseModel):
    ollama_url: str | None = None
    model: str | None = None
    openai_url: str | None = None
    openai_model: str | None = None


class PortfolioReviewInput(BaseModel):
    events: list[str] = []
    current_allocation: dict[str, float] = {}


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _http_json(method: str, url: str, body: dict | None = None, timeout: int = 30) -> dict:
    """Raw HTTP JSON call used by both providers."""
    import urllib.error
    import urllib.request

    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as exc:
        raise RuntimeError(f"HTTP error: {exc}") from exc


def _openai_chat(messages: list[dict], model: str, timeout: int = 90) -> str:
    """Call an OpenAI-compatible /v1/chat/completions endpoint.

    The base URL is read from ~/.flowcore/ai.json["openai_url"] at call time.
    Raises RuntimeError if openai_url is not configured or request fails.
    """
    cfg = _read_json("ai.json", {})
    base = cfg.get("openai_url", "").rstrip("/")
    if not base:
        raise RuntimeError("openai_url not configured")
    resolved_model = model or cfg.get("openai_model", "")
    url = f"{base}/v1/chat/completions"
    resp = _http_json("POST", url, {
        "model": resolved_model,
        "messages": messages,
        "stream": False,
    }, timeout=timeout)
    return resp["choices"][0]["message"]["content"]


def _ollama(method: str, path: str, body: dict | None = None, timeout: int = 30) -> dict:
    """Call the Ollama HTTP API; raises RuntimeError if unavailable.

    The base URL is read from ~/.flowcore/ai.json["ollama_url"] at call time
    so it can be changed (e.g. to a Tailscale IP) without restarting FlowCore.
    """
    cfg = _read_json("ai.json", {})
    base = cfg.get("ollama_url", _OLLAMA_DEFAULT).rstrip("/")
    url = f"{base}{path}"
    return _http_json(method, url, body, timeout)


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

        cfg = _read_json("ai.json", {})
        messages = data.history + [{"role": "user", "content": data.question}]

        # OpenAI-compatible provider (Hermes Agent, LM Studio, Jan, …)
        if cfg.get("openai_url"):
            oai_model = data.model or cfg.get("openai_model", "")
            try:
                answer = _openai_chat(messages, oai_model, timeout=90)
                return {"answer": answer, "provider": "openai-compat", "model": oai_model}
            except Exception:
                pass  # fall through to Ollama

        # Ollama fallback
        model = data.model or cfg.get("model", "llama3")
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
                "answer": "Nenhum provider de IA disponível. Configure openai_url ou inicie o Ollama.",
                "provider": "unavailable",
                "model": model,
                "error": str(exc),
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    # ── AI runtime / Ollama model management ─────────────────────────────────

    @app.get("/api/ai-runtime/config")
    async def ai_config_get():
        """Return current AI runtime config."""
        cfg = _read_json("ai.json", {})
        active = "openai-compat" if cfg.get("openai_url") else "ollama"
        return {
            "active_provider": active,
            "ollama_url": cfg.get("ollama_url", _OLLAMA_DEFAULT),
            "model": cfg.get("model", "phi4-mini"),
            "openai_url": cfg.get("openai_url", ""),
            "openai_model": cfg.get("openai_model", ""),
            "default_url": _OLLAMA_DEFAULT,
        }

    @app.patch("/api/ai-runtime/config")
    async def ai_config_patch(data: AIConfig):
        """Update AI runtime config without restarting FlowCore."""
        cfg = _read_json("ai.json", {})
        if data.ollama_url is not None:
            cfg["ollama_url"] = data.ollama_url.rstrip("/")
        if data.model is not None:
            cfg["model"] = data.model
        if data.openai_url is not None:
            cfg["openai_url"] = data.openai_url.rstrip("/") if data.openai_url else ""
        if data.openai_model is not None:
            cfg["openai_model"] = data.openai_model
        config_path = _DATA_DIR / "ai.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
        return {"saved": True, **cfg}

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

    # ── Market intelligence — common source for dashboard, APK and Telegram ──

    def _market_unavailable(name: str, exc: Exception) -> dict:
        return {
            "available": False,
            "source": "market_intelligence",
            "updated_at": time.time(),
            "error": f"{name}: {type(exc).__name__}",
        }

    @app.get("/api/market/fx")
    async def market_fx():
        try:
            from runtime.market_intelligence.fx_analysis import analyze_fx
            return {**analyze_fx(), "available": True, "updated_at": time.time(), "stub": False}
        except Exception as exc:
            return {"pairs": [], "usd_regime": "unknown", "stub": False, **_market_unavailable("fx", exc)}

    @app.get("/api/market/yield-curve")
    async def market_yield_curve():
        try:
            from runtime.market_intelligence.yield_curve import build_yield_curve
            return {**build_yield_curve().to_dict(), "available": True, "updated_at": time.time(), "stub": False}
        except Exception as exc:
            return {"points": [], "slope_10y_2y_bps": None, "shape": None, "interpretation": None, "stub": False, **_market_unavailable("yield_curve", exc)}

    @app.get("/api/market/watchlists")
    async def market_watchlists():
        try:
            from runtime.market_intelligence.watchlist import list_watchlists
            return {**list_watchlists(), "available": True, "updated_at": time.time(), "stub": False}
        except Exception as exc:
            return {"watchlists": [], "stub": False, **_market_unavailable("watchlists", exc)}

    @app.get("/api/market/watchlist/{watchlist}")
    async def market_watchlist_snapshot(watchlist: str):
        try:
            from runtime.market_intelligence.watchlist import snapshot
            return {**snapshot(watchlist), "available": True, "updated_at": time.time(), "stub": False}
        except Exception as exc:
            return {"watchlist": watchlist, "items": [], "stub": False, **_market_unavailable("watchlist", exc)}

    @app.get("/api/market/asset-classes")
    async def market_asset_classes():
        try:
            from runtime.market_intelligence.asset_classes import analyze_asset_classes
            return {**analyze_asset_classes(), "available": True, "updated_at": time.time(), "stub": False}
        except Exception as exc:
            return {"classes": {}, "stub": False, **_market_unavailable("asset_classes", exc)}

    @app.get("/api/market/briefing")
    async def market_briefing():
        try:
            from runtime.market_intelligence.briefing import build_briefing
            return {**build_briefing(), "available": True, "stub": False}
        except Exception as exc:
            return {"lines": [], "stub": False, **_market_unavailable("briefing", exc)}

    @app.get("/api/market/overview")
    async def market_overview():
        """Compact, cross-channel market feed used by the APK and Telegram briefing."""
        try:
            from runtime.market_intelligence.alerts import list_alerts
            from runtime.market_intelligence.source_catalog import source_snapshot
            sources = source_snapshot()
            items = []
            for observation in sources.get("official_observations", []):
                if not observation.get("available"):
                    continue
                if observation.get("instrument"):
                    items.append({
                        "symbol": observation["instrument"],
                        "label": observation.get("label", observation["instrument"]),
                        "level": observation.get("value"),
                        "delta_pct_1d": None,
                        "status": "ok",
                        "source": observation.get("source"),
                        "observation_date": observation.get("observation_date"),
                    })
                for point in observation.get("points", []):
                    items.append({
                        "symbol": point["instrument"],
                        "label": point.get("label", point["instrument"]),
                        "level": point.get("value"),
                        "delta_pct_1d": None,
                        "status": "ok",
                        "source": point.get("source"),
                        "observation_date": point.get("observation_date"),
                    })
            return {
                "items": items,
                "alerts": list_alerts(limit=8),
                "sources": sources,
                "available": True,
                "updated_at": time.time(),
                "source": "market_intelligence",
                "stub": False,
            }
        except Exception as exc:
            return {"items": [], "alerts": [], "source": "market_intelligence", "stub": False, **_market_unavailable("overview", exc)}

    @app.get("/api/market/sources")
    async def market_sources():
        """Source catalog and official observations with provenance metadata."""
        try:
            from runtime.market_intelligence.source_catalog import source_snapshot
            return {**source_snapshot(), "available": True, "stub": False}
        except Exception as exc:
            return {"catalog": [], "official_observations": [], "stub": False, **_market_unavailable("sources", exc)}

    @app.get("/api/market/rebalancing")
    async def market_rebalancing():
        return {"actions": [], "updated_at": time.time(), "mode": "requires_positions", "stub": False}

    @app.get("/api/market/alerts")
    async def market_alerts():
        try:
            from runtime.market_intelligence.alerts import evaluate_alerts, list_alerts
            return {"fired_now": evaluate_alerts(), "alerts": list_alerts(), "available": True, "updated_at": time.time(), "stub": False}
        except Exception as exc:
            return {"fired_now": [], "alerts": [], "stub": False, **_market_unavailable("alerts", exc)}

    @app.get("/api/market/calendar")
    async def market_economic_calendar():
        try:
            from runtime.market_intelligence.calendar import today_events
            return {"events": today_events(), "available": True, "updated_at": time.time(), "stub": False}
        except Exception as exc:
            return {"events": [], "stub": False, **_market_unavailable("calendar", exc)}

    @app.get("/api/market/news")
    async def market_news():
        try:
            from runtime.market_intelligence.news import fetch_news
            return {**fetch_news(max_per_group=3), "available": True, "updated_at": time.time(), "stub": False}
        except Exception as exc:
            return {"items": [], "groups": [], "stub": False, **_market_unavailable("news", exc)}

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
        portfolios = data if isinstance(data, list) else []
        reference = _load_reference_portfolio()
        if not any(p.get("id") == reference.get("id") for p in portfolios):
            portfolios = [reference, *portfolios]
        return portfolios

    @app.get("/api/portfolios/{portfolio_id}")
    async def get_portfolio(portfolio_id: str):
        portfolios = await list_portfolios()
        for p in portfolios:
            if p.get("id") == portfolio_id:
                return p
        raise HTTPException(status_code=404, detail="Portfolio not found")

    @app.get("/api/portfolios/{portfolio_id}/summary")
    async def portfolio_summary(portfolio_id: str):
        portfolio = await get_portfolio(portfolio_id)
        allocation = portfolio.get("target_allocation", [])
        return {
            "portfolio_id": portfolio_id,
            "positions": allocation,
            "total_value": portfolio.get("reference_value", 0),
            "currency": portfolio.get("currency", "BRL"),
            "mode": "reference_target_allocation",
            "stub": False,
        }

    @app.get("/api/portfolios/{portfolio_id}/exposure")
    async def portfolio_exposure(portfolio_id: str):
        portfolio = await get_portfolio(portfolio_id)
        grouped: dict[str, float] = {}
        for item in portfolio.get("target_allocation", []):
            key = item.get("class", "outros")
            grouped[key] = grouped.get(key, 0) + float(item.get("weight", 0))
        return {
            "portfolio_id": portfolio_id,
            "by_asset_class": [{"label": k, "weight": round(v, 2)} for k, v in sorted(grouped.items())],
            "by_sector": [], "by_industry": [], "by_country": [], "by_currency": [],
            "mode": "reference_target_allocation", "stub": False,
        }

    @app.get("/api/portfolios/{portfolio_id}/impact")
    async def portfolio_impact(portfolio_id: str):
        return {"portfolio_id": portfolio_id, "impact": [], "stub": True}

    @app.get("/api/portfolios/{portfolio_id}/decision")
    async def portfolio_decision(portfolio_id: str):
        portfolio = await get_portfolio(portfolio_id)
        review = _review_reference_portfolio(portfolio)
        return {
            "portfolio_id": portfolio_id,
            "decisions": [{"type": "hold_reference", "label": "Manter alvos até receber posições reais e dados de mercado"}],
            "readiness_score": 0,
            "sub_scores": {"positions": 0, "market_data": 0, "suitability": 0},
            "top_risks": review["alerts"],
            "top_opportunities": ["Diversificação por indexador, geografia e classe de ativo"],
            "review": review,
            "stub": False,
        }

    @app.get("/api/portfolios/{portfolio_id}/narrative")
    async def portfolio_narrative(portfolio_id: str):
        portfolio = await get_portfolio(portfolio_id)
        return {
            "portfolio_id": portfolio_id,
            "narrative": "Carteira-modelo moderada de R$ 1 milhão com 45% em renda fixa brasileira, 15% em renda fixa internacional, 10% em multimercados, 25% em renda variável e 4,5% em alternativos. A parcela de IA é satélite, limitada a 7% do patrimônio.",
            "review_policy": portfolio.get("review_policy", {}),
            "stub": False,
        }

    # ── Assets [STUB] ─────────────────────────────────────────────────────────

    @app.get("/api/portfolios/{portfolio_id}/review")
    async def portfolio_review(portfolio_id: str):
        portfolio = await get_portfolio(portfolio_id)
        return _review_reference_portfolio(portfolio)

    @app.post("/api/portfolios/{portfolio_id}/review")
    async def portfolio_review_post(portfolio_id: str, data: PortfolioReviewInput):
        portfolio = await get_portfolio(portfolio_id)
        return _review_reference_portfolio(portfolio, data.events, data.current_allocation)

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

    # ── Android TTS / SMS / Contacts ──────────────────────────────────────────

    class TTSRequest(BaseModel):
        text: str
        language: str = "pt-BR"
        pitch: float = 1.0
        rate: float = 1.0

    class SMSSendRequest(BaseModel):
        number: str
        message: str

    @app.post("/api/android/tts")
    async def android_tts(data: TTSRequest):
        if not data.text.strip():
            raise HTTPException(status_code=422, detail="text is required")
        try:
            from capability.adapters.android import AndroidTTSAdapter
            adapter = AndroidTTSAdapter()
            if not adapter.is_available():
                return {"spoken": False, "error": "termux-tts-speak not available",
                        "corrective_action": "pkg install termux-api"}
            result = adapter.speak(data.text, language=data.language,
                                   pitch=data.pitch, rate=data.rate)
            return {"spoken": result.success, "error": result.error if not result.success else None}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/android/sms")
    async def android_sms_inbox(limit: int = Query(20, le=100), offset: int = Query(0, ge=0)):
        try:
            from capability.adapters.android import AndroidSMSAdapter
            adapter = AndroidSMSAdapter()
            if not adapter.is_available():
                return {"messages": [], "error": "termux-sms-send not available",
                        "corrective_action": "pkg install termux-api"}
            result = adapter.inbox(limit=limit, offset=offset)
            if result.success:
                return result.data
            return {"messages": [], "error": result.error}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/android/sms")
    async def android_sms_send(data: SMSSendRequest):
        if not data.number.strip() or not data.message.strip():
            raise HTTPException(status_code=422, detail="number and message are required")
        try:
            from capability.adapters.android import AndroidSMSAdapter
            adapter = AndroidSMSAdapter()
            if not adapter.is_available():
                return {"sent": False, "error": "termux-sms-send not available"}
            result = adapter.send(data.number, data.message)
            return {"sent": result.success, "error": result.error if not result.success else None}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/api/android/contacts")
    async def android_contacts(q: str = Query(None)):
        try:
            from capability.adapters.android import AndroidContactAdapter
            adapter = AndroidContactAdapter()
            if not adapter.is_available():
                return {"contacts": [], "error": "termux-contact-list not available",
                        "corrective_action": "pkg install termux-api"}
            result = adapter.find(q) if q else adapter.list_contacts()
            if result.success:
                return result.data
            return {"contacts": [], "error": result.error}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
