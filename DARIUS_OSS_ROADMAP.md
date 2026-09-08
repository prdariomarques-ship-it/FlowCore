# DARIUS OSS — Living Architecture Roadmap
**Document Version:** 1.0.0  
**Date:** 2026-09-08  
**Scope:** Non-Core Runtime Architecture, Adapters, Boundaries, Resilience and Infrastructure

---

## 1. Roadmap Strategy & Cadence

This roadmap complements the Core Runtime (Task, State, Agent Core executed by Jules). While Jules delivers execution loop capabilities, Systems Architecture delivers foundational stability, type safety, boundary contracts, and asynchronous infrastructure.

---

## 2. Milestone Overview

```
Phase 1: Boundaries & Contracts (Current)
  ├── 1.1 Formalize Protocols (LLM, Tool, MCP, Memory, Skills, Notification)
  ├── 1.2 Telegram decoupling via NotificationChannelAdapter & Bus
  └── 1.3 Architecture conformance test suite

Phase 2: Asynchronous Job Infrastructure (In Progress)
  ├── 2.1 AsyncJobDispatcher for background worker tasks
  ├── 2.2 Pre-computed Snapshot Engine for /api/priorities and /api/intelligence
  └── 2.3 Resilient retry & circuit breaker policies

Phase 3: Extended Adapters & Tool Sandboxing
  ├── 3.1 LLMAdapter implementations (Ollama, DeepSeek, OpenRouter)
  ├── 3.2 Dynamic Tool Schema generator & MCP bridge
  └── 3.3 Three-tier memory adapter (working, episodic, semantic vector)

Phase 4: Multi-Tenant Fleet & Enterprise Hardening
  ├── 4.1 Token bucket distributed rate limiting
  ├── 4.2 Distributed tracing & structured JSON observability
  └── 4.3 Multi-device sync protocol
```

---

## 3. Work Breakdown Structure

### Phase 1: Boundaries & Contracts (Completed)
* [x] **Audit:** Comprehensive audit against roadmap (`DARIUS_OSS_AUDIT.md`).
* [x] **Architecture Specification:** Hexagonal architecture specification (`DARIUS_OSS_ARCHITECTURE.md`).
* [x] **Core Protocols:** Implement `darius/interfaces/` with `@runtime_checkable` Python Protocols.
* [x] **Telegram Decoupling:** Implement `darius/notifications/` with `TelegramNotificationAdapter` without breaking legacy `runtime/telegram.py`.
* [x] **Architecture Tests:** Automated test suite in `tests/architecture/` verifying contract adherence (50/50 passing).

### Phase 2: Asynchronous Job Engine (Completed)
* [x] **Background Dispatcher:** `darius/jobs/dispatcher.py` to offload blocking tasks from FastAPI routes with priority queuing and concurrency controls.
* [x] **Snapshot Materializer:** `darius/jobs/cache.py` TTL cache with atomic stampede protection for heavy computations.
* [x] **Telemetry & Metrics:** Measure job latency, queue depth, cache hit ratio, and failure rates.

### Phase 3: Pluggable Adapters
* [ ] **Universal LLM Adapter:** Typed Pydantic request/response model wrapping providers.
* [ ] **Tool Sandbox:** Validate arguments, verify permissions, and enforce execution budgets.
* [ ] **MCP Bidirectional Adapter:** Expose DARIUS OSS tools to external MCP clients cleanly.
