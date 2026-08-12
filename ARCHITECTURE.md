# FlowCore Architecture

## Overview

FlowCore is a lightweight, Python-based workflow automation engine designed for Android via Termux. It runs entirely in user space with no root access, no external databases, and no network exposure by default.

## System Design

```
┌─────────────────────────────────────────────────────┐
│                    flowcore.py                       │
│              (CLI Entry Point)                       │
├─────────────┬───────────────┬───────────────────────┤
│  serve      │  run          │  health / version     │
│  (API)      │  (full)       │  / selftest           │
├─────────────┴───────────────┴───────────────────────┤
│                                                     │
│  ┌──────────────┐  ┌────────────┐  ┌────────────┐  │
│  │   Runtime    │  │  Executor  │  │ Scheduler  │  │
│  │   (lifecycle)│  │  (tasks)   │  │ (cron)     │  │
│  └──────┬───────┘  └─────┬──────┘  └─────┬──────┘  │
│         │                │               │          │
│  ┌──────┴────────────────┴───────────────┴──────┐   │
│  │                  Agents                      │   │
│  │  (base.py + health_agent.py + future agents) │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │              API (FastAPI)                   │   │
│  │        bound to 127.0.0.1:8080               │   │
│  │  /api/health  /api/flows  /api/executions    │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
│  ┌──────────────┐  ┌────────────────────────────┐   │
│  │    Config    │  │      Persistence           │   │
│  │  (YAML +     │  │  (SQLite via aiosqlite)   │   │
│  │   env vars)  │  │                            │   │
│  └──────────────┘  └────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

## Modules

### config/

YAML-based configuration with environment variable overrides. The loader merges `default.yml` with `local.yml` (if present), then applies environment variable overrides using the pattern `FLOWCORE__SECTION__KEY`.

### runtime/

Manages the application lifecycle: startup, graceful shutdown, signal handling. It initializes the database, starts the scheduler, and registers agents.

### executor/

Async task execution engine. Each task has a unique ID, status tracking, retry logic with configurable delay, and timeout enforcement. Results are persisted to SQLite.

### scheduler/

Periodic task scheduling using APScheduler. Tasks can be scheduled by interval, cron expression, or one-shot execution. Timezone-aware (defaults to America/Sao_Paulo).

### api/

FastAPI REST API bound to `127.0.0.1` by default. Provides endpoints for health checks, flow management, and execution monitoring. No authentication middleware in v1.0 (trusted local access only).

### agents/

Pluggable agent framework. Each agent extends `BaseAgent` and implements `run()` and `health_check()`. Agents are registered at startup and can be triggered on-demand or on schedule.

### scripts/

Helper utilities used by CLI tools: `helpers.py` (platform detection, directory management) and `audit.py` (security and compatibility auditing).

## Data Flow

```
User/CLI ──> flowcore.py serve ──> FastAPI ──> Executor
                                          │
                                          v
                                    Scheduler ──> Agent ──> Result
                                          │
                                          v
                                    SQLite (data/flowcore.db)
```

## Security Model

| Layer | Control |
|-------|---------|
| Network | API binds to `127.0.0.1` — not accessible from network |
| Privilege | No root/sudo — runs in user space only |
| Secrets | All credentials via environment variables |
| Code | No `os.system()`, no `subprocess` with user input |
| Dependencies | Pure-Python only — no C extensions |

## Compatibility

FlowCore is tested on:

| Platform | Python | Status |
|----------|--------|--------|
| Termux (Android 12–15) | 3.11–3.13 | Supported |
| Ubuntu 22.04+ | 3.11–3.13 | Supported |
| macOS 13+ | 3.11–3.13 | Supported |

## Resource Usage

FlowCore is designed for resource-constrained environments:

| Resource | Usage |
|----------|-------|
| RAM | ~50–100 MB idle |
| Disk | ~10 MB (without dependencies) |
| CPU | Minimal (single-threaded by default) |
| Battery | Low impact (batch scheduling) |
