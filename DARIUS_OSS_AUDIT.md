# DARIUS OSS — Architectural Audit & Systems Engineering Report
**Document Version:** 1.0.0
**Date:** 2026-09-08
**Role:** Architecture + Systems Engineering
**Scope:** Complementary System Architecture (Core Runtime: Task, State, Agent Core owned by Jules)

---

## 1. Executive Summary

DARIUS OSS (built on the FlowCore foundation) is evolving from a single-device personal execution runtime on Android/Termux into a multi-device, multi-tenant personal execution operating system and wealth management copilot.

This audit analyzes the codebase across 10 strategic axes, evaluating boundary separation, adapter maturity, external service coupling (notably Telegram), scalability bottlenecks, and type safety, while formally establishing the division of responsibilities between **Core Runtime (Jules)** and **Systems Architecture (Antigravity)**.

---

## 2. Division of Responsibilities

To guarantee parallel acceleration without race conditions or code duplication:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   DARIUS OSS SYSTEM BOUNDARIES                         │
├────────────────────────────────────┬───────────────────────────────────┤
│    JULES (Core Runtime Track)      │    ANTIGRAVITY (Architecture Track)│
├────────────────────────────────────┼───────────────────────────────────┤
│ • Task definition & Task lifecycle │ • System Boundaries & Protocols   │
│ • State machine & execution graph  │ • LLM Adapters (Local/Cloud/Router)│
│ • Agent Core inner execution loop  │ • Tool, Skill & MCP Adapters      │
│ • Step runner & Agent dispatch     │ • Memory & Context Adapters       │
│                                    │ • Notification Decoupling         │
│                                    │ • Async Job Infrastructure        │
│                                    │ • Architecture Tests & Contracts  │
└────────────────────────────────────┴───────────────────────────────────┘
```

**Boundary Rule:** Antigravity provides typed protocols, abstract adapters, event pipelines, and non-blocking background infrastructure. Jules consumes these contracts to drive the core execution of tasks and states.

---

## 3. Architecture Audit Against Roadmap

| Roadmap Capability | Current Implementation | Architectural Health | Required Architectural Enhancement |
| :--- | :--- | :---: | :--- |
| **LLM Integration** | `runtime/llm/` (`LLMRouter`, Ollama, DeepSeek, OpenRouter) | **7 / 10** | Unify under `LLMAdapter` Protocol with structured Pydantic schema validation, token metering, and streaming. |
| **Tool System** | `runtime/agent/contracts.py` (`ToolSpec`), `capability/` | **6 / 10** | Decouple tools from ad-hoc dicts into `ToolAdapter` with strict schema, permission levels, and validation. |
| **MCP Integration** | `flowcore_mcp/`, `mcp_server.py` | **6 / 10** | Bridge internal tools to MCP server dynamically through `MCPAdapter` boundary without code duplication. |
| **Memory & Context**| `storage/memory_repo.py`, `runtime/intelligence/` | **5 / 10** | Introduce 3-tier memory abstraction: Working Memory (scratchpad), Episodic Memory, and Semantic Memory. |
| **Skills System** | `flows/` and hardcoded pipelines | **5 / 10** | Establish declarative `SkillManifest` contract supporting dynamic discovery, prompt injection, and capability binding. |
| **Notification Engine** | Direct `runtime/telegram.py` imports | **4 / 10** | Decouple Telegram into `NotificationChannelAdapter` with non-blocking queue, fallback, and circuit breaker. |
| **Async Jobs** | Synchronous execution in FastAPI endpoints | **4 / 10** | Create resilient `AsyncJobDispatcher` preventing HTTP request timeouts (e.g. 45s cold start on priorities). |
| **Type Safety** | Mixed Pydantic and raw `dict[str, Any]` | **6 / 10** | Enforce typed boundary contracts (`@runtime_checkable Protocol`) across all adapter entry points. |

---

## 4. Coupling Analysis: The Telegram Bottleneck

### 4.1. Findings
Currently, Telegram integration is tightly coupled across business logic modules:
1. `runtime/ai/brief_diario.py` directly calls `from runtime.telegram import send_message`.
2. `runtime/watchdog.py` directly calls `from runtime.telegram import send_message`.
3. `runtime/client_outreach.py` invokes telegram directly in dispatch logic.
4. `api/dashboard_routes.py` manages `telegram_chat_id` per office but fallback routines rely on global environment variables (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`).

### 4.2. Risks Identified
* **Thread Blocking:** `runtime/telegram.py` uses synchronous `urllib.request.urlopen` with a 10-second timeout. When Telegram API experiences latency or rate limiting (429), it blocks the entire single-process event loop on Termux.
* **Cascading Failures:** If Telegram credentials are misconfigured, `TelegramNotConfiguredError` is thrown inside background loops, potentially halting execution pipelines.
* **Multi-Tenant Leakage:** A single failure or wrong chat ID in one tenant blocks shared dispatch routines.

### 4.3. Architectural Remedy (Preserving Production Behavior)
* Wrap all notification providers under `NotificationChannelAdapter`.
* Retain `runtime.telegram.send_message` with 100% backward compatibility.
* Provide an asynchronous, buffered notification bus (`NotificationBus`) with background worker delivery, retries, and circuit breaker to protect the runtime.

---

## 5. Performance & Scalability Bottlenecks

1. **Synchronous Cold Start:**
   * `/api/priorities` and `/api/intelligence` trigger cold execution of `MarketAgent` (Yahoo Finance, BCB) and `ComplianceAgent` across all portfolios sequentially, taking up to 45.9s on mobile hardware.
   * **Solution:** Event-driven background pre-computation with an asynchronous job scheduler writing pre-computed results to in-memory/SQLite cache.

2. **In-Memory Rate Limiting:**
   * `runtime/rate_limit.py` stores request histories in process memory (`_HISTORY = defaultdict(deque)`). If the process restarts, all throttles reset.
   * **Solution:** State-isolated memory store with atomic rolling window operations.

---

## 6. Actionable Implementation Blueprint

1. **Boundary Protocols (`darius/interfaces/`):**
   - `LLMAdapter`
   - `ToolAdapter`
   - `MCPAdapter`
   - `MemoryAdapter`
   - `SkillAdapter`
   - `NotificationChannelAdapter`
2. **Resilient Notification Bus (`darius/notifications/`):**
   - Channel registry, non-blocking queue, Telegram channel adapter.
3. **Async Job & Execution Infrastructure (`darius/jobs/`):**
   - Non-blocking job runner, priority queues, telemetry and failure isolation.
4. **Architecture Tests (`tests/architecture/`):**
   - Verify zero upward imports, ensure protocol conformance, and validate Telegram decoupling.
