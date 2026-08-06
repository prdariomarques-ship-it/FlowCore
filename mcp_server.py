"""FlowCore — MCP stdio server.

Exposes memory/document commands (remember, recall, note, todo, agenda,
search, ...), flow commands (create, list, get, run, delete flows and
their executions), Android device capabilities, Outlook (read-only),
Calendar (shares Outlook's auth session), WhatsApp (via Evolution API,
already-paired instance), Telegram (reuses the spcx-monitor bot), the
SCPX Observer Framework (normalized MarketEvents, no interpretation), the
SCPX Macro Score Engine (deterministic per-dimension scores, no LLM), the
SCPX Regime Engine (deterministic threshold classification, no LLM), the
Portfolio Domain (manual portfolio/holding CRUD, live valuation, asset
classification), and a live integration status aggregator as MCP tools
so an MCP client (e.g. Claude Code) can call FlowCore directly instead
of shelling out to the CLI.

Started via: python3 flowcore.py mcp
"""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

import service
from runtime.ollama import OllamaError
from storage import DocumentRepository, MemoryRepository

ROOT = Path(__file__).resolve().parent

mcp = FastMCP("flowcore")

_doc_repo = DocumentRepository()
_mem_repo = MemoryRepository()


@mcp.tool()
def flowcore_remember(text: str) -> dict:
    """Save a memory. Use '#topic' words in the text to tag it."""
    memory = _mem_repo.add(text)
    return {"saved": True, "topics": memory.get("topics", [])}


@mcp.tool()
def flowcore_recall(topic: str) -> list[dict]:
    """Recall memories matching a topic or keyword (case-insensitive substring)."""
    return _mem_repo.search(topic)


@mcp.tool()
def flowcore_memories() -> list[dict]:
    """List all saved memories."""
    return _mem_repo.list_all()


@mcp.tool()
async def flowcore_docs() -> list[dict]:
    """List all imported documents (id, title, source, created_at)."""
    return await _doc_repo.list_all()


@mcp.tool()
async def flowcore_show(doc_id: int) -> dict:
    """Show a document's full content by its numeric ID."""
    doc = await _doc_repo.get_by_id(doc_id)
    if not doc:
        raise ValueError(f"Document not found: {doc_id}")
    return doc


@mcp.tool()
async def flowcore_import_markdown(filepath: str) -> dict:
    """Import a Markdown file into FlowCore's document store."""
    return await service.import_markdown(filepath)


@mcp.tool()
async def flowcore_search(query: str) -> dict:
    """Search both documents and memories for a query string."""
    return await service.search(query)


@mcp.tool()
async def flowcore_daily_summary() -> dict:
    """Get today's summary: document/memory/task counts and recent documents."""
    return {
        "documents": await _doc_repo.count(),
        "memories": _mem_repo.count(),
        "tasks": await _doc_repo.count_by_source("note", "todo", "agenda"),
        "recent_documents": await _doc_repo.list_recent(5),
    }


@mcp.tool()
async def flowcore_stats() -> dict:
    """Get FlowCore statistics (document count, memory count)."""
    return {
        "documents": await _doc_repo.count(),
        "memories": _mem_repo.count(),
    }


@mcp.tool()
async def flowcore_note(text: str) -> dict:
    """Add a quick note."""
    result = await service.add_note(text, "note")
    return {"id": result["id"], "saved": True}


@mcp.tool()
async def flowcore_todo(task: str) -> dict:
    """Add a TODO item."""
    result = await service.add_note(task, "todo")
    return {"id": result["id"], "saved": True}


@mcp.tool()
async def flowcore_agenda(event: str) -> dict:
    """Add an event to the agenda."""
    result = await service.add_note(event, "agenda")
    return {"id": result["id"], "saved": True}


@mcp.tool()
async def flowcore_ask(question: str, timeout: float | None = None) -> str:
    """Ask the local Ollama model a question, grounded with the 5 most recent documents as context.

    Warms up the model first if it's not already loaded in Ollama (can take
    a while on first call). `timeout` overrides FLOWCORE_OLLAMA_TIMEOUT
    (default 180s) for both the warm-up wait and the generate call.
    """
    try:
        answer, _model = await service.ask(question, timeout=timeout)
        return answer
    except OllamaError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_flow_create(name: str, steps: list[dict]) -> dict:
    """Create a flow: a named, ordered list of steps.

    Each step is {"action": <action>, "params": {...}}. Known actions:
    note, todo, agenda (params: text), ask (params: question, timeout?),
    search (params: query), import_markdown (params: filepath).
    """
    try:
        return await service.create_flow(name, steps)
    except ValueError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_flow_list() -> list[dict]:
    """List all flows."""
    return await service.list_flows()


@mcp.tool()
async def flowcore_flow_get(flow_id: int) -> dict:
    """Get a flow's definition by id."""
    try:
        return await service.get_flow(flow_id)
    except ValueError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_flow_run(flow_id: int) -> dict:
    """Run a flow now, executing each step in order. Returns the resulting execution
    (status, per-step results, real started_at/finished_at timestamps)."""
    try:
        return await service.run_flow(flow_id)
    except ValueError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_flow_delete(flow_id: int) -> dict:
    """Delete a flow by id."""
    deleted = await service.delete_flow(flow_id)
    return {"deleted": deleted}


@mcp.tool()
async def flowcore_execution_list(flow_id: int | None = None, limit: int | None = None) -> list[dict]:
    """List executions, optionally filtered by flow_id and/or capped by limit."""
    return await service.list_executions(flow_id, limit)


@mcp.tool()
async def flowcore_execution_get(execution_id: int) -> dict:
    """Get an execution's status and per-step results by id."""
    try:
        return await service.get_execution(execution_id)
    except ValueError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_battery() -> dict:
    """Get Android battery status (level, charging status, health, temperature)."""
    return await service.get_battery()


@mcp.tool()
async def flowcore_wifi() -> dict:
    """Get wifi/network info."""
    return await service.get_wifi_info()


@mcp.tool()
async def flowcore_disk_usage(path: str = "/data") -> dict:
    """Get disk usage (total/used/available) for a given path."""
    return await service.get_disk_usage(path)


@mcp.tool()
async def flowcore_clipboard_get() -> dict:
    """Read the device clipboard."""
    return await service.get_clipboard()


@mcp.tool()
async def flowcore_clipboard_set(text: str) -> dict:
    """Set the device clipboard."""
    return await service.set_clipboard(text)


@mcp.tool()
async def flowcore_notify(text: str, title: str = "FlowCore") -> dict:
    """Send an Android notification."""
    return await service.send_notification(title, text)


@mcp.tool()
async def flowcore_apps() -> dict:
    """List installed apps (Termux/Android only). Package visibility may be
    restricted by Android's package-visibility filtering."""
    return await service.list_installed_apps()


@mcp.tool()
async def flowcore_outlook_auth_start() -> dict:
    """Begin Outlook's device code flow. Returns a user_code and
    verification_uri to show the user; authorization completes in the
    background — poll flowcore_outlook_auth_status() to see when it's done.
    """
    from runtime.outlook import OutlookError

    try:
        return await service.outlook_auth_start()
    except OutlookError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_outlook_auth_status() -> dict:
    """Poll Outlook device code flow status (idle/pending/complete/failed) and
    whether a valid authenticated session currently exists."""
    return await service.outlook_auth_status()


@mcp.tool()
async def flowcore_outlook_messages(limit: int = 10) -> list[dict]:
    """List the latest Outlook messages (read-only)."""
    from runtime.outlook import OutlookError

    try:
        return await service.outlook_messages(limit)
    except OutlookError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_outlook_unread() -> int:
    """Get the Outlook inbox unread count."""
    from runtime.outlook import OutlookError

    try:
        return await service.outlook_unread_count()
    except OutlookError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_outlook_search(query: str, limit: int = 10) -> list[dict]:
    """Search Outlook messages (read-only)."""
    from runtime.outlook import OutlookError

    try:
        return await service.outlook_search(query, limit)
    except OutlookError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_calendar_today() -> list[dict]:
    """List today's calendar events. Shares auth with Outlook — use
    flowcore_outlook_auth_start if not yet authenticated."""
    from runtime.calendar import CalendarError

    try:
        return await service.calendar_today()
    except CalendarError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_calendar_tomorrow() -> list[dict]:
    """List tomorrow's calendar events."""
    from runtime.calendar import CalendarError

    try:
        return await service.calendar_tomorrow()
    except CalendarError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_calendar_week() -> list[dict]:
    """List this week's calendar events."""
    from runtime.calendar import CalendarError

    try:
        return await service.calendar_week()
    except CalendarError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_calendar_next() -> dict | None:
    """Get the next upcoming calendar event (within 30 days), or None."""
    from runtime.calendar import CalendarError

    try:
        return await service.calendar_next()
    except CalendarError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_calendar_search(query: str, limit: int = 10) -> list[dict]:
    """Search calendar events."""
    from runtime.calendar import CalendarError

    try:
        return await service.calendar_search(query, limit)
    except CalendarError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_calendar_create(
    subject: str,
    start: str,
    end: str,
    timezone: str = "UTC",
    description: str = "",
    location: str = "",
    attendees: list[str] | None = None,
) -> dict:
    """Create a calendar event. start/end are ISO 8601 datetimes without an
    offset (e.g. "2026-08-10T10:00:00"), interpreted in `timezone`."""
    from runtime.calendar import CalendarError

    try:
        return await service.calendar_create(subject, start, end, timezone, description, location, attendees)
    except CalendarError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_calendar_update(
    event_id: str,
    subject: str | None = None,
    start: str | None = None,
    end: str | None = None,
    timezone: str | None = None,
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
) -> dict:
    """Update a calendar event. Only pass the fields you want to change."""
    from runtime.calendar import CalendarError

    fields = {
        k: v
        for k, v in {
            "subject": subject,
            "start": start,
            "end": end,
            "description": description,
            "location": location,
            "attendees": attendees,
        }.items()
        if v is not None
    }
    if timezone is not None and ("start" in fields or "end" in fields):
        fields["timezone_"] = timezone
    if not fields:
        raise RuntimeError("No fields given to update.")
    try:
        return await service.calendar_update(event_id, **fields)
    except CalendarError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_calendar_delete(event_id: str) -> dict:
    """Delete a calendar event."""
    from runtime.calendar import CalendarError

    try:
        await service.calendar_delete(event_id)
        return {"deleted": True}
    except CalendarError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_whatsapp_health() -> dict:
    """Check whether the Evolution API server is reachable. No instance/API key needed."""
    from runtime.whatsapp import WhatsAppError

    try:
        return await service.whatsapp_health()
    except WhatsAppError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_whatsapp_status() -> dict:
    """Get the configured WhatsApp instance's connection state (open/close/connecting)."""
    from runtime.whatsapp import WhatsAppError

    try:
        return await service.whatsapp_status()
    except WhatsAppError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_whatsapp_send(number: str, text: str) -> dict:
    """Send a WhatsApp message through the already-paired Evolution API instance.
    number: destination in international format, digits only (e.g. "5511999999999")."""
    from runtime.whatsapp import WhatsAppError

    try:
        return await service.whatsapp_send(number, text)
    except WhatsAppError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_integrations_status() -> list[dict]:
    """Live health/latency for every connected integration (Outlook/Calendar,
    WhatsApp, Ollama). Probed fresh on every call — no history."""
    return await service.integrations_status()


@mcp.tool()
async def flowcore_telegram_health() -> dict:
    """Verify the Telegram bot token is valid (calls getMe). Reuses the
    spcx-monitor bot — not a separate FlowCore-dedicated bot."""
    from runtime.telegram import TelegramError

    try:
        return await service.telegram_health()
    except TelegramError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_telegram_config() -> dict:
    """Static check: are TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID set. No network call."""
    return await service.telegram_configuration()


@mcp.tool()
async def flowcore_telegram_send(text: str, chat_id: str | None = None) -> dict:
    """Send a Telegram message via the spcx-monitor bot. chat_id overrides
    TELEGRAM_CHAT_ID for this message only."""
    from runtime.telegram import TelegramError

    try:
        return await service.telegram_send(text, chat_id)
    except TelegramError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_observer_registry() -> list[dict]:
    """SCPX Observer Framework — list registered observers (source, category,
    symbol). No network call, pure introspection."""
    return await service.observer_registry_info()


@mcp.tool()
async def flowcore_observer_events() -> list[dict]:
    """Run every registered SCPX Observer now and return normalized
    MarketEvents. Observers only observe — no interpretation/scoring/
    recommendations happen here."""
    return await service.observer_events()


@mcp.tool()
async def flowcore_observer_event(source: str) -> list[dict]:
    """Run a single SCPX Observer by name (treasury, dollar, vix, oil,
    gold) and return its MarketEvent(s)."""
    from runtime.observers.registry import registry
    from runtime.observers.base import ObserverError

    if source not in registry.names():
        raise RuntimeError(f"Unknown observer: {source!r}")
    try:
        return await service.observer_source_events(source)
    except ObserverError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_observer_health() -> dict:
    """Live reachability probe for the SCPX Observer Framework (runs the vix observer)."""
    from runtime.observers.base import ObserverError

    try:
        return await service.observer_health()
    except ObserverError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_macro_score_dimensions() -> dict:
    """SCPX Macro Score Engine — dimension -> source mapping. No computation."""
    return await service.macro_score_dimensions()


@mcp.tool()
async def flowcore_macro_score_scores() -> list[dict]:
    """Compute every SCPX macro dimension's score now. Deterministic, no LLM —
    status is "insufficient_data" (score=None) for any dimension without
    enough persisted history yet, never a fabricated number."""
    return await service.macro_score_compute_all()


@mcp.tool()
async def flowcore_macro_score_score(dimension: str) -> dict:
    """Compute a single SCPX macro dimension's score by name (commodities,
    liquidity, risk_sentiment)."""
    from runtime.macro_score import MacroScoreError

    try:
        return await service.macro_score_compute(dimension)
    except MacroScoreError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_regime_signals() -> list[dict]:
    """SCPX Regime Engine — classify every dimension's regime now
    (elevated/depressed/neutral/insufficient_data). Deterministic
    threshold classification, no LLM, no fused "master regime"."""
    return await service.regime_classify_all()


@mcp.tool()
async def flowcore_regime_signal(dimension: str) -> dict:
    """Classify a single SCPX dimension's regime by name (commodities,
    liquidity, risk_sentiment)."""
    from runtime.macro_score import MacroScoreError

    try:
        return await service.regime_classify(dimension)
    except MacroScoreError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_portfolio_create(name: str) -> dict:
    """Create a portfolio (Sprint 21 Portfolio Domain)."""
    return await service.create_portfolio(name)


@mcp.tool()
async def flowcore_portfolio_list() -> list[dict]:
    """List all portfolios."""
    return await service.list_portfolios()


@mcp.tool()
async def flowcore_portfolio_get(portfolio_id: int) -> dict:
    """Get a portfolio by id."""
    try:
        return await service.get_portfolio(portfolio_id)
    except ValueError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_portfolio_delete(portfolio_id: int) -> dict:
    """Delete a portfolio (cascades to its holdings)."""
    deleted = await service.delete_portfolio(portfolio_id)
    return {"deleted": deleted}


@mcp.tool()
async def flowcore_portfolio_summary(portfolio_id: int) -> dict:
    """Live totals for a portfolio (market value, cost basis, unrealized
    gain) — simple sums, not exposure analysis (that's a later phase)."""
    try:
        return await service.portfolio_summary(portfolio_id)
    except ValueError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_holding_add(
    portfolio_id: int, symbol: str, quantity: float, average_cost: float, currency: str = "USD"
) -> dict:
    """Add a holding to a portfolio. Triggers best-effort automatic asset
    classification (via yfinance) if the symbol hasn't been seen before —
    never blocks the add if classification fails."""
    try:
        return await service.add_holding(portfolio_id, symbol, quantity, average_cost, currency)
    except ValueError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_holding_list(portfolio_id: int) -> list[dict]:
    """List a portfolio's holdings, each enriched with a live market value
    (recomputed every call, never persisted) and its asset classification."""
    try:
        return await service.list_holdings(portfolio_id)
    except ValueError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_holding_update(
    holding_id: int, quantity: float | None = None, average_cost: float | None = None
) -> dict:
    """Update a holding's quantity and/or average cost."""
    try:
        return await service.update_holding(holding_id, quantity, average_cost)
    except ValueError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_holding_delete(holding_id: int) -> dict:
    """Delete a holding."""
    deleted = await service.delete_holding(holding_id)
    return {"deleted": deleted}


@mcp.tool()
async def flowcore_asset_get(symbol: str) -> dict:
    """Get an asset's classification (name, sector, industry, country,
    currency, asset_class, and any manually-tagged attributes)."""
    try:
        return await service.get_asset(symbol)
    except ValueError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool()
async def flowcore_asset_tag(
    symbol: str,
    theme: str | None = None,
    duration: str | None = None,
    credit_quality: str | None = None,
    liquidity: str | None = None,
    income_generation: str | None = None,
    inflation_protection: str | None = None,
    currency_protection: str | None = None,
    risk_attributes: str | None = None,
    region: str | None = None,
    interest_rate_sensitivity: str | None = None,
    growth_profile: str | None = None,
    correlation_group: str | None = None,
) -> dict:
    """Manually tag an asset's soft attributes — merges with whatever is
    already stored, never fabricated or auto-fetched.

    Parameter names must match runtime.portfolio.attributes.ASSET_ATTRIBUTE_FIELDS
    exactly (the canonical schema every interface derives from) — unlike
    the API/CLI, MCP tools need a real Python signature for schema
    introspection, so this list can't be generated at runtime. Enforced
    by tests/portfolio/test_attributes_schema.py, not just this comment.
    """
    return await service.tag_asset(
        symbol,
        theme=theme,
        duration=duration,
        credit_quality=credit_quality,
        liquidity=liquidity,
        income_generation=income_generation,
        inflation_protection=inflation_protection,
        currency_protection=currency_protection,
        risk_attributes=risk_attributes,
        region=region,
        interest_rate_sensitivity=interest_rate_sensitivity,
        growth_profile=growth_profile,
        correlation_group=correlation_group,
    )


def run() -> None:
    mcp.run(transport="stdio")
