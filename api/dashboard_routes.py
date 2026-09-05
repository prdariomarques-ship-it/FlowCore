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
    ollama_fallback_url: str | None = None
    fallback_model: str | None = None


class PortfolioReviewInput(BaseModel):
    events: list[str] = []
    current_allocation: dict[str, float] = {}


class TTSRequest(BaseModel):
    text: str
    language: str = "pt-BR"
    pitch: float = 1.0
    rate: float = 1.0


class SMSSendRequest(BaseModel):
    number: str
    message: str


class RoutingPinRequest(BaseModel):
    task: str
    model_id: str


class BenchmarkRequest(BaseModel):
    model_id: str
    task_ids: list[str] | None = None


class MemoryRequest(BaseModel):
    content: str
    origin: str = "user_input"
    source: str = "chat"
    scope: str = "persistent"
    tags: list[str] = []
    confidence: float = 1.0


class MemoryInvalidateRequest(BaseModel):
    reason: str = ""


class BriefRequest(BaseModel):
    use_llm: bool = True
    send_telegram: bool = False


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _tcp_reachable(url: str, timeout: float = 3.0) -> bool:
    """Quick TCP probe so an unreachable AI endpoint fails in ~3s instead of
    burning the full request timeout (90s/180s) — without this, the chat UI
    looked hung for minutes whenever the configured PC/phone Ollama wasn't
    actually up, instead of failing over (or reporting unavailable) fast."""
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


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
        if cfg.get("openai_url") and _tcp_reachable(cfg["openai_url"]):
            oai_model = data.model or cfg.get("openai_model", "")
            try:
                answer = _openai_chat(messages, oai_model, timeout=90)
                return {"answer": answer, "provider": "openai-compat", "model": oai_model}
            except Exception:
                pass  # fall through to Ollama

        # Ollama with failover: try the primary endpoint (e.g. the desktop PC
        # over LAN) first, then a fallback endpoint (e.g. Ollama running on
        # the phone itself) if the primary is unreachable. The two legs can
        # use different models since phone hardware is usually weaker.
        primary_url = cfg.get("ollama_url", _OLLAMA_DEFAULT).rstrip("/")
        fallback_url = (cfg.get("ollama_fallback_url") or "").rstrip("/")
        primary_model = data.model or cfg.get("model", "llama3")
        fallback_model = data.model or cfg.get("fallback_model") or primary_model

        candidates = [("pc", primary_url, primary_model, 90)]
        if fallback_url and fallback_url != primary_url:
            candidates.append(("celular", fallback_url, fallback_model, 180))

        last_error: Exception | None = None
        for label, base, model, timeout in candidates:
            if not _tcp_reachable(base):
                last_error = RuntimeError(f"{label} endpoint unreachable: {base}")
                continue
            try:
                resp = _http_json("POST", f"{base}/api/chat", {
                    "model": model,
                    "messages": messages,
                    "stream": False,
                }, timeout=timeout)
                answer = resp.get("message", {}).get("content", "")
                return {"answer": answer, "provider": f"ollama-{label}", "model": model}
            except Exception as exc:  # noqa: BLE001 - try next candidate
                last_error = exc
                continue

        return {
            "answer": "Nenhum provider de IA disponível. Configure openai_url ou inicie o Ollama.",
            "provider": "unavailable",
            "model": primary_model,
            "error": str(last_error) if last_error else "no Ollama endpoint configured",
        }

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
            "ollama_fallback_url": cfg.get("ollama_fallback_url", ""),
            "fallback_model": cfg.get("fallback_model", ""),
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
        if data.ollama_fallback_url is not None:
            cfg["ollama_fallback_url"] = data.ollama_fallback_url.rstrip("/") if data.ollama_fallback_url else ""
        if data.fallback_model is not None:
            cfg["fallback_model"] = data.fallback_model
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

    # ── AI v2 — Model Registry, Router, Benchmark, Memory ───────────────────

    @app.get("/api/ai/registry")
    async def ai_registry_list():
        """List all models in the Model Registry."""
        from runtime.ai.model_registry import get_registry
        reg = get_registry()
        cfg = _read_json("ai.json", {})
        ollama_url = cfg.get("ollama_url", _OLLAMA_DEFAULT)
        synced = reg.sync_from_ollama(ollama_url)
        return {
            "models": [m.to_dict() for m in reg.list_all()],
            "synced_from_ollama": synced,
            "total": len(reg.list_all()),
        }

    @app.get("/api/ai/routing")
    async def ai_routing_table():
        """Return the full routing table (task → model)."""
        from runtime.ai.router import get_router
        router = get_router()
        return {"routing": router.routing_table(), "rules": router.get_rules()}

    @app.post("/api/ai/routing/pin")
    async def ai_routing_pin(data: RoutingPinRequest):
        """Pin a model for a specific task type."""
        from runtime.ai.router import get_router, TASK_TYPES
        if data.task not in TASK_TYPES:
            raise HTTPException(status_code=422, detail=f"task must be one of {list(TASK_TYPES)}")
        get_router().pin(data.task, data.model_id)
        return {"pinned": True, "task": data.task, "model_id": data.model_id}

    @app.delete("/api/ai/routing/pin/{task}")
    async def ai_routing_unpin(task: str):
        """Remove a pinned model for a task type."""
        from runtime.ai.router import get_router
        get_router().unpin(task)
        return {"unpinned": True, "task": task}

    @app.post("/api/ai/benchmark")
    async def ai_benchmark_run(data: BenchmarkRequest):
        """Run benchmark tasks against a model. Runs in background — returns immediately."""
        import asyncio
        from runtime.ai.benchmark import get_benchmark
        cfg = _read_json("ai.json", {})
        ollama_url = cfg.get("ollama_url", _OLLAMA_DEFAULT)

        async def _run():
            import concurrent.futures
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                await loop.run_in_executor(
                    pool,
                    lambda: get_benchmark().run(data.model_id, ollama_url=ollama_url, task_ids=data.task_ids),
                )

        asyncio.create_task(_run())
        return {"started": True, "model_id": data.model_id, "task_ids": data.task_ids}

    @app.get("/api/ai/benchmark/history")
    async def ai_benchmark_history(model_id: str | None = Query(None), limit: int = Query(10)):
        """Return benchmark run history."""
        from runtime.ai.benchmark import get_benchmark
        return {"runs": get_benchmark().history(model_id=model_id, limit=limit)}

    @app.get("/api/ai/benchmark/compare")
    async def ai_benchmark_compare(model_a: str = Query(...), model_b: str = Query(...)):
        """Compare two models using their latest benchmark results."""
        from runtime.ai.benchmark import get_benchmark
        return get_benchmark().compare(model_a, model_b)

    # ── AI Memory Engine ──────────────────────────────────────────────────────

    @app.get("/api/ai/memory")
    async def memory_search(
        q: str = Query(""),
        tags: str = Query(""),
        origin: str | None = Query(None),
        limit: int = Query(20),
    ):
        from runtime.ai.memory import get_memory
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        mem = get_memory()
        results = mem.search(q, tags=tag_list, origin=origin, limit=limit)
        return {"entries": [e.to_dict() for e in results], "stats": mem.stats()}

    @app.post("/api/ai/memory")
    async def memory_remember(data: MemoryRequest):
        from runtime.ai.memory import get_memory, ORIGINS
        if data.origin not in ORIGINS:
            raise HTTPException(status_code=422, detail=f"origin must be one of {list(ORIGINS)}")
        entry = get_memory().remember(
            data.content,
            origin=data.origin,
            source=data.source,
            scope=data.scope,
            tags=data.tags,
            confidence=data.confidence,
        )
        return {"saved": True, "entry": entry.to_dict()}

    @app.delete("/api/ai/memory/{entry_id}")
    async def memory_delete(entry_id: str):
        from runtime.ai.memory import get_memory
        deleted = get_memory().delete(entry_id)
        return {"deleted": deleted, "id": entry_id}

    @app.post("/api/ai/memory/{entry_id}/invalidate")
    async def memory_invalidate(entry_id: str, data: MemoryInvalidateRequest):
        from runtime.ai.memory import get_memory
        ok = get_memory().invalidate(entry_id, reason=data.reason)
        return {"invalidated": ok, "id": entry_id}

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
            return {"pairs": [], "usd_regime": "unknown", "dxy_delta_pct_1d": None, "stub": False, **_market_unavailable("fx", exc)}

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

    @app.post("/api/market/close")
    async def market_close():
        """Prepare o fechamento de mercado: dados reais + versão para
        cliente + versão para Instagram, salvos em
        ~/.flowcore/market_close/<data>.json."""
        try:
            from runtime.market_intelligence.market_close import build_market_close
            return {**build_market_close(), "available": True, "stub": False}
        except Exception as exc:
            return {
                "raw_lines": [], "client_version": "", "instagram_version": "",
                "stub": False, **_market_unavailable("close", exc),
            }

    @app.get("/api/market/overview")
    async def market_overview():
        """Compact, cross-channel market feed used by the APK and Telegram briefing."""
        try:
            from runtime.market_intelligence.alerts import evaluate_alerts, list_alerts
            from runtime.market_intelligence.source_catalog import source_snapshot
            evaluate_alerts()  # nothing else runs this on a schedule — without it the
            # alerts table never gets populated and this card always reads empty.
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

    @app.get("/api/market/snapshot")
    async def market_snapshot():
        """Public-source macro and market snapshot with field-level provenance."""
        try:
            from runtime.market_data.fetcher import fetch_snapshot
            return fetch_snapshot()
        except Exception as exc:
            return {
                "brl_usd": None, "selic_rate": None, "ipca_12m": None,
                "ibov_last": None, "ibov_change_pct": None, "observations": {},
                "timestamp": datetime.now(timezone.utc).isoformat(), "stub": False,
                **_market_unavailable("snapshot", exc),
            }

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
    async def market_news(
        section: str = Query("all", min_length=2, max_length=20),
        cursor: str | None = Query(None, max_length=12),
        limit: int = Query(12, ge=1, le=30),
    ):
        """Source-attributed financial headlines for web, mobile and briefing consumers."""
        try:
            from runtime.market_intelligence.news import SUPPORTED_NEWS_SECTIONS, fetch_news
            if section not in SUPPORTED_NEWS_SECTIONS:
                raise HTTPException(status_code=422, detail=f"unsupported news section: {section}")
            return {
                **fetch_news(section=section, cursor=cursor, limit=limit),
                "available": True,
                "updated_at": time.time(),
                "stub": False,
            }
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            return {
                "items": [], "groups": [], "section": section, "supported_sections": [],
                "next_cursor": None, "partial_errors": [], "stub": False,
                **_market_unavailable("news", exc),
            }

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

    # ── Brief Diário ─────────────────────────────────────────────────────────

    @app.get("/api/brief/diario")
    async def brief_get():
        """Return the last generated brief (from cache) or generate a new one."""
        from runtime.ai.brief_diario import get_last_brief, build_brief
        cached = get_last_brief()
        if cached:
            return {**cached, "from_cache": True}
        import asyncio, concurrent.futures
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            brief = await loop.run_in_executor(pool, lambda: build_brief(use_llm=False))
        return {**brief, "from_cache": False}

    @app.post("/api/brief/diario")
    async def brief_generate(data: BriefRequest):
        """Generate a fresh brief and optionally send to Telegram."""
        import asyncio, concurrent.futures
        from runtime.ai.brief_diario import build_brief, send_brief_to_telegram
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            brief = await loop.run_in_executor(pool, lambda: build_brief(use_llm=data.use_llm))
        telegram_sent = False
        if data.send_telegram:
            telegram_sent = send_brief_to_telegram(brief)
        return {**brief, "from_cache": False, "telegram_sent": telegram_sent}

    @app.get("/api/brief/history")
    async def brief_history():
        """Return last 30 brief summaries."""
        from pathlib import Path
        import json as _json
        hist_path = Path.home() / ".flowcore" / "brief_history.json"
        if hist_path.exists():
            try:
                return {"history": _json.loads(hist_path.read_text())}
            except Exception:
                pass
        return {"history": []}

    # ── Observability / Metrics ───────────────────────────────────────────────

    @app.get("/api/metrics")
    async def metrics():
        """Internal FlowCore metrics — request counts, latency, AI calls."""
        from runtime.observability import get_metrics
        return get_metrics()

    @app.post("/api/metrics/reset")
    async def metrics_reset():
        """Reset in-process metrics counters."""
        from runtime.observability import reset_metrics
        reset_metrics()
        return {"reset": True}

    # ── Scheduler ─────────────────────────────────────────────────────────────

    _BRIEF_JOB_NAME = "brief_diario"
    _BRIEF_JOB_SCRIPT = str(Path(__file__).resolve().parents[1] / "scripts" / "brief_diario_job.py")
    # 07:30 BRT = 10:30 UTC, weekdays
    _BRIEF_JOB_CRON = "30 10 * * 1-5"

    @app.get("/api/scheduler/jobs")
    async def scheduler_list():
        from runtime.job_scheduler import JobScheduler
        return {"jobs": JobScheduler().list_jobs()}

    @app.post("/api/scheduler/brief/enable")
    async def scheduler_brief_enable():
        """Register daily morning brief cron job (07:30 BRT, weekdays)."""
        from runtime.job_scheduler import JobScheduler
        sched = JobScheduler()
        try:
            ok = sched.add_job(_BRIEF_JOB_NAME, _BRIEF_JOB_SCRIPT, _BRIEF_JOB_CRON)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        return {"enabled": ok, "schedule": _BRIEF_JOB_CRON, "script": _BRIEF_JOB_SCRIPT}

    @app.delete("/api/scheduler/brief/enable")
    async def scheduler_brief_disable():
        """Unregister the daily morning brief cron job."""
        from runtime.job_scheduler import JobScheduler
        removed = JobScheduler().remove_job(_BRIEF_JOB_NAME)
        return {"disabled": removed}

    @app.post("/api/scheduler/brief/run-now")
    async def scheduler_brief_run_now():
        """Trigger the brief job immediately (blocking — may take up to 2 min with LLM)."""
        import asyncio, concurrent.futures
        from runtime.ai.brief_diario import build_brief, send_brief_to_telegram
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            brief = await loop.run_in_executor(pool, lambda: build_brief(use_llm=True))
        sent = send_brief_to_telegram(brief)
        return {
            "sent": sent,
            "llm_applied": bool(brief.get("llm_polish")),
            "llm_error": brief.get("llm_error"),
            "generated_at": brief["generated_at"],
            "sections_ok": sum(1 for s in brief["sections"].values() if s.get("ok")),
        }
