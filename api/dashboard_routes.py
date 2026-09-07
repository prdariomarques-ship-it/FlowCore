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

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Query, Request
from pydantic import BaseModel, field_validator

_OLLAMA_DEFAULT = "http://localhost:11434"
_DATA_DIR = Path.home() / ".flowcore"

# Single source of truth for the office's investment policy (fase 0:
# office-scoped, backed by storage/client_repo.py) lives in
# runtime/portfolio/reference.py — shared with agents/compliance_agent.py
# so an edit here is immediately visible to compliance evaluation too,
# not just to this module. Every call site below must pass the office_id
# resolved from the authenticated session (api.tenant_auth.get_current_user)
# — never a hardcoded default, or one office could read/edit another's policy.
from runtime.portfolio.reference import load_reference_portfolio as _load_reference_portfolio
from api.tenant_auth import get_current_user


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


_COMPLIANCE_KEYWORDS = (
    "desenquadr", "fora do limite", "acima do limite", "abaixo do limite",
    "compliance", "fora da politica", "fora da política",
)


def _is_compliance_question(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in _COMPLIANCE_KEYWORDS)


async def _answer_compliance_question(office_id: str) -> str:
    """Real-data answer for "quais clientes estão desenquadrados hoje?",
    sourced straight from ComplianceAgent — same data as GET /api/alerts,
    just formatted as chat prose instead of a JSON list."""
    from agents.compliance_agent import ComplianceAgent

    result = await ComplianceAgent().run({"office_id": office_id})
    violations = result["data"]["violations"]
    portfolios = result["data"]["portfolios"]

    if not violations:
        evaluated = [p for p in portfolios if p["status"] in ("NORMAL", "ATENCAO", "DESENQUADRADO")]
        if evaluated:
            return "Nenhuma carteira desenquadrada no momento. Todas as posições avaliadas estão dentro dos limites."
        return (
            "Não há posição atual conhecida para nenhuma carteira, então não é possível calcular "
            "desenquadramento agora. Configure a posição atual da carteira para ativar esta checagem."
        )

    lines = [f"**{len(violations)} violação(ões) de alocação encontrada(s):**", ""]
    for v in violations:
        icon = "🔴" if v["severity"] == "CRITICAL" else "🟡"
        lines.append(f"- {icon} **{v['client_name']}** — {v['message']}")
    return "\n".join(lines)


_MARKET_KEYWORDS = (
    "mercado", "ibovespa", "s&p", "s&p500", "nasdaq", "dólar", "dolar", "usd/brl",
    "treasury", "juros americano", "di jan", "petróleo", "petroleo", "ouro", "cobre",
    "movimento de mercado", "indicador",
)
_INTELLIGENCE_KEYWORDS = (
    "override", "recalibr", "inteligência", "inteligencia",
    "o que mudou na carteira", "o que mudou nas prioridades", "o que mudou hoje",
    "por que essa carteira", "por que a carteira", "por que está em alerta",
    "por que esta em alerta", "tese", "muda a tese",
)
_PRIORITY_KEYWORDS = (
    "prioridade", "priorizar", "o que fazer primeiro", "mais urgente", "por onde começar", "por onde comecar",
)


def _is_market_question(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in _MARKET_KEYWORDS)


def _is_intelligence_question(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in _INTELLIGENCE_KEYWORDS)


def _is_priority_question(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in _PRIORITY_KEYWORDS)


async def _answer_market_question(office_id: str) -> str:
    """Real-data answer for "o que mudou no mercado hoje?", sourced from
    MarketAgent — same data as GET /api/market, formatted as chat prose."""
    from agents.market_agent import MarketAgent

    result = await MarketAgent().run()
    data = result["data"]
    movements = data["movements"]
    relevant = [m for m in movements if m["relevance"] in ("HIGH", "MEDIUM")]

    status_label = {"NORMAL": "sem movimentos relevantes", "ATTENTION": "atenção", "ALERT": "alerta"}
    lines = [f"**Mercado hoje: {status_label.get(data['market_status'], data['market_status'])}**", ""]

    if not relevant:
        observed = [m for m in movements if m["current_value"] is not None]
        if not observed:
            return "Não há dados de mercado disponíveis no momento (fonte indisponível)."
        lines.append("Nenhum indicador se moveu o suficiente para ser destacado hoje.")
        return "\n".join(lines)

    for m in relevant:
        icon = "🔴" if m["relevance"] == "HIGH" else "🟡"
        mock_tag = " *(MOCK — sem fonte real conectada)*" if m["source"] == "MOCK" else ""
        direction = "subiu" if (m["change"] or 0) >= 0 else "caiu"
        unit = "p.p." if m["unit"] == "percentage_points" else "%"
        lines.append(f"- {icon} **{m['asset']}** {direction} {abs(m['change']):.2f}{unit}{mock_tag}")
    return "\n".join(lines)


async def _answer_intelligence_question(office_id: str) -> str:
    """Real-data answer for "por que essa carteira está em alerta?" /
    "explique esse override", sourced from IntelligenceEngine — same data
    as GET /api/intelligence, formatted as chat prose."""
    from agents.intelligence_engine import IntelligenceEngine

    result = await IntelligenceEngine().run({"office_id": office_id})
    events = result["data"]["events"]
    overrides = [e for e in events if e["status"] == "OVERRIDE"]
    recalibrates = [e for e in events if e["status"] == "RECALIBRATE"]

    if not overrides and not recalibrates:
        return "Nenhum evento de recalibração ou override no momento — situação estável."

    lines = []
    if overrides:
        lines.append(f"**{len(overrides)} override(s) — a tese original não se sustenta mais:**")
        lines.append("")
        for e in overrides:
            lines.append(f"- 🔴 {e['reason']}")
            lines.append(f"  - Antes: {e.get('previous_thesis', '—')}")
            lines.append(f"  - Agora: {e.get('new_information', '—')}")
            if e.get("affected_portfolios"):
                lines.append(f"  - Carteiras afetadas: {', '.join(e['affected_portfolios'])}")
            lines.append(f"  - Sugestão: {e.get('suggested_action', '—')}")
        lines.append("")
    if recalibrates:
        lines.append(f"**{len(recalibrates)} recalibração(ões):**")
        lines.append("")
        for e in recalibrates:
            lines.append(f"- 🟡 {e['reason']} — {e.get('suggested_action', '—')}")
    return "\n".join(lines)


async def _answer_priority_question(office_id: str) -> str:
    """Real-data answer for "o que priorizar hoje?", sourced from
    PriorityEngine — same data as GET /api/priorities."""
    from agents.priority_engine import PriorityEngine

    result = await PriorityEngine().run({"office_id": office_id})
    items = result["data"]["items"]
    if not items:
        return "Nenhuma prioridade no momento — nada exige atenção imediata."

    lines = ["**Prioridades de hoje (ordem decrescente):**", ""]
    for i, item in enumerate(items, start=1):
        icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🔵", "NEUTRAL": "⚪"}.get(item["level"], "⚪")
        lines.append(f"{i}. {icon} **{item['title']}** — {item['reason']}")
    return "\n".join(lines)


# ── Request schemas (module-level so FastAPI resolves them correctly) ──────────

class SignupRequest(BaseModel):
    office_name: str
    name: str
    email: str
    password: str

    @field_validator("password")
    @classmethod
    def _password_meets_nist_minimum(cls, value: str) -> str:
        # NIST 800-63b: enforce a minimum length, not composition rules
        # (no forced uppercase/digit/symbol — those push users toward
        # predictable patterns without actually raising entropy). Upper
        # bound is only to cap the cost of hashing pathological input.
        if len(value) < 8:
            raise ValueError("A senha precisa ter pelo menos 8 caracteres.")
        if len(value) > 128:
            raise ValueError("A senha pode ter no máximo 128 caracteres.")
        return value

    @field_validator("email")
    @classmethod
    def _email_looks_like_an_email(cls, value: str) -> str:
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("Informe um email válido.")
        return value


class LoginRequest(BaseModel):
    email: str
    password: str


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


class ReferencePortfolioUpdate(BaseModel):
    """Partial update for the editable reference portfolio — only fields
    provided are changed, same convention as AIConfig/ai_config_patch."""
    name: str | None = None
    reference_value: float | None = None
    target_allocation: list[dict[str, Any]] | None = None
    sleeve_limits: dict[str, float] | None = None
    review_policy: dict[str, Any] | None = None
    current_allocation: dict[str, float] | None = None


class DemoClientUpdate(BaseModel):
    """Partial update for one demo client's position — same partial-merge
    convention as ReferencePortfolioUpdate."""
    current_allocation: dict[str, float]


class ClientContactUpdate(BaseModel):
    """Real contact info for one client, entered explicitly — never
    inferred or defaulted. Empty string clears the field; omitted field
    leaves it untouched (same partial-update convention used everywhere
    else in this module)."""
    email: str | None = None
    phone: str | None = None


class ReviewRequestSend(BaseModel):
    channels: list[str] = ["email", "whatsapp"]


class OfficeNotificationsUpdate(BaseModel):
    """The office's own Telegram destination for autonomous-agent
    notifications (agents/orchestrator.py). None/empty clears it -- an
    office with none configured simply gets no autonomous Telegram
    alert, never a fabricated delivery."""
    telegram_chat_id: str | None = None


class AgentApprovalEdit(BaseModel):
    """The "EDITAR" step of the approval queue (§9) -- replaces the
    pending approval's whole prepared payload (e.g. a tweaked draft
    subject/body) before a human approves it. Deliberately a free-form
    dict, not a rigid schema: action_type already varies what payload
    means (today only "contact_client", see agents/orchestrator.py)."""
    payload: dict[str, Any]


class AdvisorProfileUpdate(BaseModel):
    """Partial update for the dashboard's advisor card — same
    partial-merge convention as AIConfig/ai_config_patch. Deliberately no
    photo field: see the /api/advisor handlers for why the avatar is
    initials-only rather than an uploaded/generated image."""
    name: str | None = None
    title: str | None = None
    quote: str | None = None


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

    # ── Auth (fase 0: multi-office login) ────────────────────────────────────
    # Distinct from api/auth.py's require_api_token (a single device-wide
    # shared secret, the pre-fase-0 "Personal Execution OS" model) — this
    # is per-user, per-office login on top of it. See storage/tenant_repo.py
    # and api/tenant_auth.py for the full rationale.

    @app.post("/api/auth/signup")
    async def auth_signup(data: SignupRequest, request: Request):
        from storage.tenant_repo import TenantRepository
        from storage.client_repo import ClientRepository

        tenant_repo = TenantRepository()
        # The very first office ever created on this install gets the 27
        # example clients seeded (the same demo data this project has been
        # showing throughout development) — every office after that starts
        # empty, because a real signup must never show a paying customer
        # fabricated clients that aren't theirs.
        is_first_office = await tenant_repo.count_offices() == 0
        office = await tenant_repo.create_office(data.office_name)
        try:
            user = await tenant_repo.create_user(office["id"], data.email, data.password, data.name, role="owner")
        except ValueError:
            raise HTTPException(status_code=409, detail="Este email já está cadastrado.")
        await ClientRepository().seed_office(office["id"], with_demo_clients=is_first_office)
        session = await tenant_repo.create_session(
            user["id"], user_agent=request.headers.get("User-Agent"),
            ip_address=request.client.host if request.client else None,
        )
        return {"token": session["token"], "user": user, "office": office}

    @app.post("/api/auth/login")
    async def auth_login(data: LoginRequest, request: Request):
        """Throttled per OWASP's Authentication Cheat Sheet: an
        unbounded login endpoint is a standing invitation to credential
        stuffing / brute force. 5 failed attempts in 15 minutes blocks
        further attempts for that email until the window rolls off —
        checked before verifying the password so a locked-out attacker
        can't keep guessing while blocked."""
        from storage.tenant_repo import TenantRepository

        tenant_repo = TenantRepository()
        if await tenant_repo.is_rate_limited(data.email):
            raise HTTPException(
                status_code=429,
                detail="Muitas tentativas de login. Tente novamente em alguns minutos.",
            )
        user = await tenant_repo.verify_password(data.email, data.password)
        await tenant_repo.record_login_attempt(data.email, success=bool(user))
        if not user:
            raise HTTPException(status_code=401, detail="Email ou senha inválidos.")
        session = await tenant_repo.create_session(
            user["id"], user_agent=request.headers.get("User-Agent"),
            ip_address=request.client.host if request.client else None,
        )
        return {"token": session["token"], "user": user}

    @app.post("/api/auth/logout")
    async def auth_logout(request: Request):
        from storage.tenant_repo import TenantRepository

        token = None
        header = request.headers.get("Authorization")
        if header and header.startswith("Bearer "):
            token = header[len("Bearer "):].strip()
        if token:
            await TenantRepository().delete_session(token)
        return {"logged_out": True}

    @app.get("/api/auth/me")
    async def auth_me(request: Request):
        return await get_current_user(request)

    @app.get("/api/auth/sessions")
    async def auth_sessions_list(request: Request):
        """Every device/browser currently logged into this user's
        account -- the real "Terminais Autorizados" equivalent, backed
        by storage/tenant_repo.py's sessions table rather than invented
        hardware-security-module data."""
        from storage.tenant_repo import TenantRepository

        user = await get_current_user(request)
        header = request.headers.get("Authorization")
        token = header[len("Bearer "):].strip() if header and header.startswith("Bearer ") else None
        tenant_repo = TenantRepository()
        current_id = await tenant_repo.get_session_id(token) if token else None
        sessions = await tenant_repo.list_sessions(user["id"])
        for s in sessions:
            s["current"] = s["id"] == current_id
        return {"sessions": sessions}

    @app.delete("/api/auth/sessions/{session_id}")
    async def auth_sessions_delete(session_id: str, request: Request):
        from storage.tenant_repo import TenantRepository

        user = await get_current_user(request)
        deleted = await TenantRepository().delete_session_by_id(user["id"], session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="unknown session")
        return {"deleted": True}

    # ── Agent chat (/api/ask) ──────────────────────────────────────────────────

    @app.post("/api/ask")
    async def ask(data: AskRequest, request: Request):
        if not data.question.strip():
            raise HTTPException(status_code=422, detail="question is required")

        # Wealth Copilot questions are real-data lookups, not something an
        # LLM should guess at — answer them directly from the relevant
        # agent instead of routing through OpenAI/Ollama. Checked in this
        # order because "priorizar"/"override"/"mercado" questions are
        # more specific than a generic compliance question and should not
        # be swallowed by broader keyword sets. Same "never 5xx" contract
        # as the JSON agent endpoints (/api/alerts, /api/market, ...): an
        # agent failure degrades to an honest chat message, not a 500 —
        # except a missing/invalid session, which still 401s (a chat
        # answer can't be scoped to an office without one).
        agent_intents = (
            (_is_compliance_question, _answer_compliance_question, "flowcore-compliance-agent"),
            (_is_priority_question, _answer_priority_question, "flowcore-priority-engine"),
            (_is_market_question, _answer_market_question, "flowcore-market-agent"),
            (_is_intelligence_question, _answer_intelligence_question, "flowcore-intelligence-engine"),
        )
        for matches, answer_fn, provider in agent_intents:
            if matches(data.question):
                user = await get_current_user(request)
                try:
                    answer = await answer_fn(user["office_id"])
                except Exception as exc:  # noqa: BLE001 - degrade, never 500
                    answer = f"Não foi possível consultar os dados agora ({type(exc).__name__}). Tente novamente em instantes."
                return {"answer": answer, "provider": provider, "model": ""}

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

        # Last resort: DeepSeek via the shared LLM Router -- the same
        # infra the autonomous agents already use (agents/orchestrator.py),
        # reused rather than a third hand-rolled cloud client. Only
        # reached once neither local Ollama endpoint answered -- local-
        # first is preserved, DeepSeek is the fallback, never the first
        # choice. See runtime/llm/policy.py's LocalFirstPolicy: this is
        # the one call site in the interactive chat that opts into cloud.
        try:
            from runtime.llm import LLMRequest
            from service import _llm_router

            office_id = None
            try:
                office_id = (await get_current_user(request))["office_id"]
            except HTTPException:
                pass  # unauthenticated chat still gets a cloud fallback; just no cost attribution
            # Flatten the conversation (messages already includes prior
            # turns + this question) into one prompt -- LLMRequest takes a
            # single string, unlike Ollama's /api/chat message-list shape.
            history_text = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
            llm_request = LLMRequest(
                prompt=history_text,
                metadata={"allow_cloud": True, "purpose": "chat", "office_id": office_id},
            )
            response = await asyncio.to_thread(_llm_router.generate, llm_request)
            return {"answer": response.text, "provider": response.provider, "model": response.model}
        except Exception as exc:  # noqa: BLE001 - genuinely out of options
            last_error = exc

        return {
            "answer": "Nenhum provider de IA disponível. Configure openai_url ou inicie o Ollama.",
            "provider": "unavailable",
            "model": primary_model,
            "error": str(last_error) if last_error else "no Ollama endpoint configured",
        }

    # ── Advisor profile (dashboard's Advisor card) ───────────────────────────
    # Name/title/quote only — deliberately no photo field. The desktop
    # mockup this card follows shows a photographic headshot, but
    # generating a realistic "photo" of the app's actual named user would
    # fabricate a likeness of a real person, which is a different and
    # more serious problem than the demo clients' fictitious names. The
    # card instead renders an initials avatar (same pattern as the demo
    # client avatars) from whatever name is configured here; a real photo
    # can be added as a future upload feature if the team wants one.

    _ADVISOR_DEFAULT = {
        "name": "Dário Marques", "title": "Especialista em Investimentos",
        "quote": "Estratégia transforma informação em liberdade.",
    }

    @app.get("/api/advisor")
    async def advisor_get(request: Request):
        # Per-office file (fase 0): defaults to the logged-in user's own
        # name, not a hardcoded one — otherwise every new office would see
        # "Dário Marques" on its Advisor card regardless of who signed up.
        user = await get_current_user(request)
        default = {**_ADVISOR_DEFAULT, "name": user["name"]}
        return {**default, **_read_json(f"advisor_{user['office_id']}.json", {})}

    @app.put("/api/advisor")
    async def advisor_put(data: AdvisorProfileUpdate, request: Request):
        user = await get_current_user(request)
        default = {**_ADVISOR_DEFAULT, "name": user["name"]}
        cfg = {**default, **_read_json(f"advisor_{user['office_id']}.json", {})}
        cfg.update({k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None})
        config_path = _DATA_DIR / f"advisor_{user['office_id']}.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"saved": True, **cfg}

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

    # ── Reference portfolio — editable model portfolio ──────────────────────
    #
    # The reference portfolio (target_allocation + sleeve_limits +
    # review_policy + current_allocation) is FlowCore's only real allocation
    # policy today; these three endpoints let it be customized without a
    # redeploy. Edits persist to ~/.flowcore/portfolio_moderate_1m.json
    # (runtime/portfolio/reference.py) and are picked up immediately by
    # ComplianceAgent and by every /api/portfolios* route below — there is
    # exactly one loader now, not two independent copies.

    @app.get("/api/portfolio/reference")
    async def portfolio_reference_get(request: Request):
        from runtime.portfolio.reference import is_customized
        user = await get_current_user(request)
        policy = await _load_reference_portfolio(user["office_id"])
        return {**policy, "is_customized": await is_customized(user["office_id"])}

    @app.put("/api/portfolio/reference")
    async def portfolio_reference_put(data: ReferencePortfolioUpdate, request: Request):
        from runtime.portfolio.reference import save_reference_portfolio
        user = await get_current_user(request)
        updated = await save_reference_portfolio(user["office_id"], data.model_dump(exclude_unset=True))
        return {"saved": True, **updated, "is_customized": True}

    @app.post("/api/portfolio/reference/reset")
    async def portfolio_reference_reset(request: Request):
        from runtime.portfolio.reference import reset_reference_portfolio
        user = await get_current_user(request)
        reset = await reset_reference_portfolio(user["office_id"])
        return {"reset": True, **reset, "is_customized": False}

    # ── Clients — real (or, for the bootstrap office, explicitly-fictitious
    # example) clients (runtime/portfolio/demo_clients.py). Every response
    # carries is_demo per-client so example data is never presented as real.

    @app.get("/api/clients/demo")
    async def demo_clients_list(request: Request):
        from runtime.portfolio.demo_clients import load_demo_clients

        user = await get_current_user(request)
        return {"clients": await load_demo_clients(user["office_id"])}

    @app.put("/api/clients/demo/{client_id}")
    async def demo_client_update(client_id: str, data: DemoClientUpdate, request: Request):
        from runtime.portfolio.demo_clients import save_demo_client

        user = await get_current_user(request)
        try:
            updated = await save_demo_client(user["office_id"], client_id, data.current_allocation)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown demo client: {client_id}")
        return {"saved": True, "client": updated}

    @app.post("/api/clients/demo/reset")
    async def demo_clients_reset(request: Request):
        from runtime.portfolio.demo_clients import reset_demo_clients

        user = await get_current_user(request)
        return {"reset": True, "clients": await reset_demo_clients(user["office_id"])}

    @app.put("/api/clients/demo/{client_id}/contact")
    async def demo_client_contact_update(client_id: str, data: ClientContactUpdate, request: Request):
        """Real contact info for a real client — the 27 example clients
        never have one (see storage/client_repo.py's seed_office), so
        this is only meaningful for clients an office actually enters."""
        from storage.client_repo import ClientRepository

        user = await get_current_user(request)
        try:
            updated = await ClientRepository().save_client_contact(user["office_id"], client_id, data.email, data.phone)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown client: {client_id}")
        return {"saved": True, "client": updated}

    # ── Client review-request outreach (email + WhatsApp) ───────────────────
    # Turns a real ComplianceAgent violation into a drafted invitation to a
    # review meeting. Never sent automatically — see
    # runtime/client_outreach.py's module docstring for why this is
    # explicit-approval-per-client only, triggered by the advisor from the
    # dashboard, never a background job.

    async def _advisor_and_office_names(office_id: str) -> tuple[str, str]:
        from storage.tenant_repo import TenantRepository

        advisor = {**_ADVISOR_DEFAULT, **_read_json(f"advisor_{office_id}.json", {})}
        office = await TenantRepository().get_office(office_id)
        return advisor["name"], (office["name"] if office else "")

    @app.get("/api/clients/review-requests")
    async def review_requests_list(request: Request):
        """One entry per client with at least one open compliance
        violation AND a real client record (the office's own policy
        "carteira" isn't itself emailable) — the drafted email/WhatsApp
        text, and whether each channel actually has somewhere to send to."""
        from agents.compliance_agent import ComplianceAgent
        from runtime.client_outreach import draft_review_request
        from storage.client_repo import ClientRepository

        user = await get_current_user(request)
        office_id = user["office_id"]
        try:
            result = await ComplianceAgent().run({"office_id": office_id})
            violations_by_client: dict[str, list[dict]] = {}
            for v in result["data"]["violations"]:
                violations_by_client.setdefault(v["client_id"], []).append(v)

            advisor_name, office_name = await _advisor_and_office_names(office_id)
            repo = ClientRepository()
            items = []
            for client_id, violations in violations_by_client.items():
                client = await repo.get_client(office_id, client_id)
                if client is None:
                    continue  # not a real, contactable client (e.g. the office's own policy)
                draft = draft_review_request(client["name"], violations, advisor_name, office_name)
                items.append({
                    "client_id": client_id, "client_name": client["name"],
                    "severity": "CRITICAL" if any(v["severity"] == "CRITICAL" for v in violations) else "WARNING",
                    "violations": violations, "is_demo": client["is_demo"],
                    "email": client["email"], "phone": client["phone"],
                    "can_send_email": bool(client["email"]), "can_send_whatsapp": bool(client["phone"]),
                    "draft": draft,
                })
            return {"total": len(items), "items": items, "available": True}
        except Exception as exc:
            return {"total": 0, "items": [], "stub": False, **_market_unavailable("review-requests", exc)}

    @app.post("/api/clients/{client_id}/request-review")
    async def client_request_review(client_id: str, data: ReviewRequestSend, request: Request):
        """The actual send — an explicit, human-triggered action. Every
        channel result is honest: "sent", "no_contact_info", "not_configured",
        or "error", never a fabricated success."""
        from agents.compliance_agent import ComplianceAgent
        from runtime.client_outreach import draft_review_request, send_review_request
        from storage.client_repo import ClientRepository

        user = await get_current_user(request)
        office_id = user["office_id"]
        repo = ClientRepository()
        client = await repo.get_client(office_id, client_id)
        if client is None:
            raise HTTPException(status_code=404, detail=f"unknown client: {client_id}")

        result = await ComplianceAgent().run({"office_id": office_id})
        violations = [v for v in result["data"]["violations"] if v["client_id"] == client_id]
        if not violations:
            raise HTTPException(status_code=400, detail="Este cliente não possui violações abertas no momento.")

        advisor_name, office_name = await _advisor_and_office_names(office_id)
        draft = draft_review_request(client["name"], violations, advisor_name, office_name)
        results = send_review_request(office_id, client, draft, data.channels, user["id"])
        return {"client_id": client_id, "channels": results}

    # ── Client 360 (Fase 1 of the Office OS scope) ───────────────────────────
    # One consolidated view of a real client: their position, whether
    # ComplianceAgent currently flags it, and every past outreach attempt —
    # assembled from data these other modules already compute, nothing new
    # invented here.

    _COMPLIANCE_TO_HEALTH = {
        "NORMAL": "SAUDAVEL", "ATENCAO": "ATENCAO", "DESENQUADRADO": "DESENQUADRADO",
        "SEM_POSICAO_ATUAL": "SEM_POSICAO_ATUAL", "SEM_REGRAS_DEFINIDAS": "SEM_REGRAS_DEFINIDAS",
    }

    @app.get("/api/clients/{client_id}/360")
    async def client_360(client_id: str, request: Request):
        from agents.compliance_agent import ComplianceAgent
        from runtime.client_outreach import outreach_history
        from storage.client_repo import ClientRepository

        user = await get_current_user(request)
        office_id = user["office_id"]
        client = await ClientRepository().get_client(office_id, client_id)
        if client is None:
            raise HTTPException(status_code=404, detail=f"unknown client: {client_id}")

        result = await ComplianceAgent().run({"office_id": office_id})
        portfolio = next((p for p in result["data"]["portfolios"] if p["portfolio_id"] == client_id), None)
        compliance_status = portfolio["status"] if portfolio else "SEM_POSICAO_ATUAL"
        violations = portfolio["violations"] if portfolio else []

        return {
            "client": client,
            "compliance": {"status": compliance_status, "violations": violations},
            "health": _COMPLIANCE_TO_HEALTH.get(compliance_status, compliance_status),
            "outreach_history": outreach_history(office_id, client_id),
        }

    # ── Autonomous Agent Runtime observability + notification config ────────
    # §18 of the Agent Runtime architecture: an advisor must be able to see
    # what the autonomous agents have actually done, not just trust that
    # something happened in the background. Read-only -- the events
    # themselves are only ever created by agents/observer_loop.py.

    @app.get("/api/agent-events")
    async def agent_events_list(request: Request, status: str | None = Query(default=None), limit: int = Query(default=50, le=200)):
        from storage.agent_event_repo import AgentEventRepository

        user = await get_current_user(request)
        events = await AgentEventRepository().list_events(user["office_id"], status=status, limit=limit)
        return {"total": len(events), "items": events}

    @app.get("/api/office/notifications")
    async def office_notifications_get(request: Request):
        from storage.tenant_repo import TenantRepository

        user = await get_current_user(request)
        office = await TenantRepository().get_office(user["office_id"])
        return {"telegram_chat_id": office["telegram_chat_id"] if office else None}

    @app.put("/api/office/notifications")
    async def office_notifications_put(data: OfficeNotificationsUpdate, request: Request):
        from storage.tenant_repo import TenantRepository

        user = await get_current_user(request)
        office = await TenantRepository().set_telegram_chat_id(user["office_id"], data.telegram_chat_id)
        return {"saved": True, "telegram_chat_id": office["telegram_chat_id"] if office else None}

    @app.get("/api/office/notifications/discover-chat-id")
    async def office_notifications_discover(request: Request):
        """Lists chats the office's Telegram bot has recently seen a
        message from -- lets the dashboard replace the manual "curl
        getUpdates, read raw JSON, copy a number" workflow with a picker.
        Requires the advisor to have already messaged the bot at least
        once (Telegram's own getUpdates rule -- no way around it)."""
        from runtime.telegram import TelegramError, TelegramNotConfiguredError, get_recent_chats

        await get_current_user(request)
        try:
            chats = await asyncio.to_thread(get_recent_chats)
        except TelegramNotConfiguredError:
            return {"available": False, "reason": "not_configured", "chats": []}
        except TelegramError as e:
            return {"available": False, "reason": str(e), "chats": []}
        return {"available": True, "chats": chats}

    # ── Human-in-the-loop approval queue (§9) ────────────────────────────────
    # LEVEL 3+ actions an agent prepares (agents/orchestrator.py) but never
    # executes alone land here as "pending" -- only a human approving from
    # this API (or the dashboard's approval cards) actually triggers the
    # send. Persisted, not a browser confirm() dialog: closing the tab
    # doesn't lose it.

    @app.get("/api/agent-approvals")
    async def agent_approvals_list(request: Request, status: str | None = Query(default=None), limit: int = Query(default=50, le=200)):
        from storage.agent_approval_repo import AgentApprovalRepository

        user = await get_current_user(request)
        approvals = await AgentApprovalRepository().list_approvals(user["office_id"], status=status, limit=limit)
        return {"total": len(approvals), "items": approvals}

    @app.put("/api/agent-approvals/{approval_id}")
    async def agent_approval_edit(approval_id: str, data: AgentApprovalEdit, request: Request):
        from storage.agent_approval_repo import AgentApprovalRepository

        user = await get_current_user(request)
        try:
            updated = await AgentApprovalRepository().update_payload(user["office_id"], approval_id, data.payload)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown approval: {approval_id}")
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return {"approval": updated}

    @app.post("/api/agent-approvals/{approval_id}/approve")
    async def agent_approval_approve(approval_id: str, request: Request):
        from runtime.client_outreach import send_review_request
        from storage.agent_approval_repo import AgentApprovalRepository
        from storage.client_repo import ClientRepository

        user = await get_current_user(request)
        office_id = user["office_id"]
        approval_repo = AgentApprovalRepository()
        approval = await approval_repo.get(office_id, approval_id)
        if approval is None:
            raise HTTPException(status_code=404, detail=f"unknown approval: {approval_id}")

        if approval["action_type"] != "contact_client":
            raise HTTPException(status_code=400, detail=f"unsupported action_type: {approval['action_type']}")

        client_id = approval["payload"]["client_id"]
        client = await ClientRepository().get_client(office_id, client_id)
        if client is None:
            raise HTTPException(status_code=404, detail=f"unknown client: {client_id}")

        # Fetches the client fresh (not the payload's snapshot) so contact
        # info added after the agent proposed this action is actually used.
        draft = approval["payload"]["draft"]
        channels = approval["payload"].get("channels", ["email", "whatsapp"])
        results = send_review_request(office_id, client, draft, channels, user["id"])

        try:
            updated = await approval_repo.decide(office_id, approval_id, "approved", user["id"], result={"channels": results})
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return {"approval": updated}

    @app.post("/api/agent-approvals/{approval_id}/reject")
    async def agent_approval_reject(approval_id: str, request: Request):
        from storage.agent_approval_repo import AgentApprovalRepository

        user = await get_current_user(request)
        office_id = user["office_id"]
        approval_repo = AgentApprovalRepository()
        approval = await approval_repo.get(office_id, approval_id)
        if approval is None:
            raise HTTPException(status_code=404, detail=f"unknown approval: {approval_id}")
        try:
            updated = await approval_repo.decide(office_id, approval_id, "rejected", user["id"])
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return {"approval": updated}

    @app.get("/api/agents/dashboard")
    async def agents_dashboard(request: Request):
        """Aggregated observability data for the Agent Runtime (§18/§25):
        is the autonomous loop actually running, what has it seen, what's
        waiting on a human, and what has it cost. One call so the frontend
        panel doesn't have to fan out to five endpoints and interleave
        loading states."""
        import os as _os

        from storage.agent_approval_repo import AgentApprovalRepository
        from storage.agent_event_repo import AgentEventRepository
        from storage.llm_call_repo import LLMCallRepository

        user = await get_current_user(request)
        office_id = user["office_id"]

        event_repo = AgentEventRepository()
        approval_repo = AgentApprovalRepository()
        llm_repo = LLMCallRepository()

        events_by_status, events_by_type, approvals_by_status, recent_events = await asyncio.gather(
            event_repo.count_by_status(office_id),
            event_repo.count_by_type(office_id),
            approval_repo.count_by_status(office_id),
            event_repo.list_events(office_id, limit=20),
        )

        # app.state.agent_scheduler doesn't exist at all under
        # create_app(version="test") -- see api/router.py's wiring -- so
        # this can't assume the attribute is even set, only that it might
        # be None (apscheduler missing) or a real SchedulerService.
        scheduler = getattr(request.app.state, "agent_scheduler", None)
        scheduler_status = {
            "enabled": scheduler is not None,
            "running": scheduler.is_running if scheduler is not None else False,
            "interval_seconds": int(_os.environ.get("FLOWCORE_AGENT_OBSERVE_INTERVAL_SECONDS", "300")),
            "tasks": scheduler.list_tasks() if scheduler is not None else [],
        }

        return {
            "scheduler": scheduler_status,
            "events": {
                "by_status": events_by_status,
                "by_type": events_by_type,
                "total": sum(events_by_status.values()),
            },
            "approvals": {
                "by_status": approvals_by_status,
                "pending": approvals_by_status.get("pending", 0),
            },
            "llm_usage": {
                # Scoped to this office's own agent-reasoning calls
                # (agents/orchestrator.py sets office_id on every request
                # it makes) -- never another office's spend, and never
                # the interactive /api/ask chat, which carries no office
                # attribution today.
                "today": llm_repo.summary(86400, office_id=office_id),
                "last_7d": llm_repo.summary(7 * 86400, office_id=office_id),
                "last_30d": llm_repo.summary(30 * 86400, office_id=office_id),
            },
            "recent_activity": recent_events,
        }

    @app.get("/api/portfolio/risk-breakdown")
    async def portfolio_risk_breakdown(request: Request):
        """Aggregate allocation by category (Renda Fixa/Renda Variável/
        Multimercado/Alternativos) for the dashboard's "Risco da Carteira
        Agregada" donut. See runtime/portfolio/risk_breakdown.py for why
        this grouping never double-counts."""
        user = await get_current_user(request)
        try:
            from runtime.portfolio.risk_breakdown import compute_risk_breakdown
            return {**(await compute_risk_breakdown(user["office_id"])), "available": True}
        except Exception as exc:
            return {"categories": [], "source": "unavailable", "available": False, "error": str(exc)}

    # ── Portfolios [STUB + file-backed list] ──────────────────────────────────
    # storage/portfolio_repo.py's PortfolioRepository (personal brokerage
    # holdings, pre-dating multi-tenancy) has no office_id column yet, so
    # it's deliberately not merged in here — see agents/compliance_agent.py's
    # module docstring for the same gap and why it isn't papered over.

    async def _list_portfolios_for(office_id: str) -> list[dict]:
        reference = await _load_reference_portfolio(office_id)
        return [reference]

    async def _get_portfolio_for(office_id: str, portfolio_id: str) -> dict:
        for p in await _list_portfolios_for(office_id):
            if p.get("id") == portfolio_id:
                return p
        raise HTTPException(status_code=404, detail="Portfolio not found")

    @app.get("/api/portfolios")
    async def list_portfolios(request: Request):
        user = await get_current_user(request)
        return await _list_portfolios_for(user["office_id"])

    @app.get("/api/portfolios/{portfolio_id}")
    async def get_portfolio(portfolio_id: str, request: Request):
        user = await get_current_user(request)
        return await _get_portfolio_for(user["office_id"], portfolio_id)

    @app.get("/api/portfolios/{portfolio_id}/summary")
    async def portfolio_summary(portfolio_id: str, request: Request):
        user = await get_current_user(request)
        portfolio = await _get_portfolio_for(user["office_id"], portfolio_id)
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
    async def portfolio_exposure(portfolio_id: str, request: Request):
        user = await get_current_user(request)
        portfolio = await _get_portfolio_for(user["office_id"], portfolio_id)
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
    async def portfolio_decision(portfolio_id: str, request: Request):
        user = await get_current_user(request)
        portfolio = await _get_portfolio_for(user["office_id"], portfolio_id)
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
    async def portfolio_narrative(portfolio_id: str, request: Request):
        user = await get_current_user(request)
        portfolio = await _get_portfolio_for(user["office_id"], portfolio_id)
        return {
            "portfolio_id": portfolio_id,
            "narrative": "Carteira-modelo moderada de R$ 1 milhão com 45% em renda fixa brasileira, 15% em renda fixa internacional, 10% em multimercados, 25% em renda variável e 4,5% em alternativos. A parcela de IA é satélite, limitada a 7% do patrimônio.",
            "review_policy": portfolio.get("review_policy", {}),
            "stub": False,
        }

    # ── Compliance — desenquadramento de carteira ───────────────────────────

    @app.get("/api/alerts")
    async def alerts(request: Request):
        """Alertas de desenquadramento (ComplianceAgent), para a aba Ações
        do APK/web e para o chat responder "quais clientes estão
        desenquadrados?". Nunca inventa posição: uma carteira sem posição
        atual conhecida ou sem política de alocação associada aparece em
        `portfolios` com o status correspondente e zero violações — não é
        omitida nem contada como falso "dentro do limite"."""
        user = await get_current_user(request)  # 401 outside the try below —
        # a missing/invalid session is not an "agent unavailable" degrade.
        try:
            from agents.compliance_agent import ComplianceAgent
            from storage.client_repo import ClientRepository

            office_id = user["office_id"]
            result = await ComplianceAgent().run({"office_id": office_id})
            violations = result["data"]["violations"]
            # A violation's client_id can be the office's own reference
            # policy (e.g. "moderate-ia-1m"), not a real client record —
            # is_client tells the frontend which rows can actually be
            # opened (Client 360) or contacted (outreach), instead of
            # letting either action 404 on a portfolio that isn't a person.
            client_ids = {c["id"] for c in await ClientRepository().list_clients(office_id)}
            items = [
                {
                    "client_id": v["client_id"], "client_name": v["client_name"], "type": v["type"],
                    "current": v["current"], "limit": v["limit"], "diff": v["diff"],
                    "severity": v["severity"], "message": v["message"], "is_demo": v.get("is_demo", False),
                    "is_client": v["client_id"] in client_ids,
                }
                for v in violations
            ]
            critical = sum(1 for v in items if v["severity"] == "CRITICAL")
            warnings = sum(1 for v in items if v["severity"] == "WARNING")
            return {
                "total": len(items), "critical": critical, "warnings": warnings, "items": items,
                "portfolios": result["data"]["portfolios"], "available": True, "stub": False,
            }
        except Exception as exc:
            return {
                "total": 0, "critical": 0, "warnings": 0, "items": [], "portfolios": [],
                "stub": False, **_market_unavailable("alerts", exc),
            }

    # ── Intelligence — MarketAgent (Wealth Copilot MVP 2, phase 1) ───────────

    @app.get("/api/market")
    async def market_agent_snapshot(request: Request):
        """MarketAgent's classified market snapshot — real levels/deltas
        from watchlist.py (yfinance) for every indicator except DI Jan
        (no B3 futures feed connected; that one entry alone carries
        source="MOCK" and is never blended with the live ones). Market
        data itself isn't office-scoped (the same market for everyone),
        but the endpoint still requires a valid session for consistency
        with the rest of the dashboard."""
        await get_current_user(request)
        try:
            from agents.market_agent import MarketAgent
            result = await MarketAgent().run()
            return {**result["data"], "available": True, "stub": False}
        except Exception as exc:
            return {
                "timestamp": None, "market_status": "NORMAL", "movements": [],
                "relevant_changes": [], "potential_impacts": [], "intelligence_events": [],
                "stub": False, **_market_unavailable("market", exc),
            }

    @app.get("/api/intelligence")
    async def intelligence_events(request: Request):
        """IntelligenceEngine's classified events (Wealth Copilot MVP 2,
        phase 2) — NEUTRAL/RECALIBRATE/OVERRIDE over the current
        MarketAgent snapshot and this office's ComplianceAgent violations.
        Every classification is also appended to this office's own
        ~/.flowcore/intelligence_audit_<office_id>.jsonl (see
        IntelligenceEngine's _audit)."""
        user = await get_current_user(request)
        try:
            from agents.intelligence_engine import IntelligenceEngine
            result = await IntelligenceEngine().run({"office_id": user["office_id"]})
            events = result["data"]["events"]
            return {
                "total": len(events),
                "override": sum(1 for e in events if e["status"] == "OVERRIDE"),
                "recalibrate": sum(1 for e in events if e["status"] == "RECALIBRATE"),
                "neutral": sum(1 for e in events if e["status"] == "NEUTRAL"),
                "events": events, "available": True, "stub": False,
            }
        except Exception as exc:
            return {
                "total": 0, "override": 0, "recalibrate": 0, "neutral": 0, "events": [],
                "stub": False, **_market_unavailable("intelligence", exc),
            }

    @app.get("/api/priorities")
    async def priorities(request: Request):
        """PriorityEngine's ranked events (Wealth Copilot MVP 2, phase 3)
        — same IntelligenceEngine events as /api/intelligence, ordered
        CRITICAL first. Never executes anything; ranking only."""
        user = await get_current_user(request)
        try:
            from agents.priority_engine import PriorityEngine
            result = await PriorityEngine().run({"office_id": user["office_id"]})
            return {**result["data"], "available": True, "stub": False}
        except Exception as exc:
            return {
                "total": 0, "by_level": {}, "items": [],
                "stub": False, **_market_unavailable("priorities", exc),
            }

    # ── Assets [STUB] ─────────────────────────────────────────────────────────

    @app.get("/api/portfolios/{portfolio_id}/review")
    async def portfolio_review(portfolio_id: str, request: Request):
        user = await get_current_user(request)
        portfolio = await _get_portfolio_for(user["office_id"], portfolio_id)
        return _review_reference_portfolio(portfolio)

    @app.post("/api/portfolios/{portfolio_id}/review")
    async def portfolio_review_post(portfolio_id: str, data: PortfolioReviewInput, request: Request):
        user = await get_current_user(request)
        portfolio = await _get_portfolio_for(user["office_id"], portfolio_id)
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
