# FlowCore Architecture

## Overview

FlowCore is a Cognitive Platform — not a chatbot. It is composed of independent
layers that allow AI agents to request capabilities without ever knowing the
underlying system commands.

**Core rule:** The LLM never executes Linux commands. The LLM requests only capabilities.
`getBattery()` resolves through the Capability Registry → Provider Resolver →
Bridge Layer → OS. The agent never knows about `termux-battery-status` or `ip addr`.

## Target Platforms

| Platform     | Status      |
|--------------|-------------|
| Android      | Supported   |
| Termux       | Supported   |
| Ubuntu/Linux | Supported   |
| macOS        | Supported   |
| Docker       | Planned     |
| Oracle Cloud | Planned     |
| Windows      | Planned     |

## Architecture Layers

```
┌─────────────────────────────────────────────────────────┐
│              Presentation Layer                          │
│          (CLI / REST API / MCP Tools)                    │
├─────────────────────────────────────────────────────────┤
│              Intent Layer                                │
│       (parse user input → structured intent)             │
├─────────────────────────────────────────────────────────┤
│              Reasoning Layer                             │
│         (Agents with Passport — cannot run               │
│          without valid Passport issued by Registry)       │
├─────────────────────────────────────────────────────────┤
│              Context Engine                              │
│   WorkspaceScanner | ProjectClassifier | ArtifactDetector│
│   ContextSerializer → flowcore.context.json              │
├─────────────────────────────────────────────────────────┤
│              Execution Engine                            │
│      Task Queue | Retry | Timeout | Semaphore            │
├─────────────────────────────────────────────────────────┤
│              Runtime Manager                             │
│   Lifecycle | Health | Passport Issuer | Boot Sequence   │
├─────────────────────────────────────────────────────────┤
│         Capability Registry + Provider Resolver          │
│   getBattery → [AndroidBridge, TermuxBridge, ShellBridge]│
├─────────────────────────────────────────────────────────┤
│              Bridge Layer                                │
│  AndroidBridge | TermuxBridge | LinuxBridge | ...        │
├─────────────────────────────────────────────────────────┤
│              Storage Layer                               │
│     DocumentRepository | MemoryRepository                │
├─────────────────────────────────────────────────────────┤
│              Operating System                            │
│           Android | Linux | macOS | Docker               │
└─────────────────────────────────────────────────────────┘
```

## Android & Termux Model

```
Android (SO Principal)
    └── FlowCore Mobile
            └── FlowCore Runtime
                    └── Android Bridge  ← BatteryManager, WiFi, Camera, Notifications
                    └── Termux Bridge   ← Python, Git, SSH, SQLite, Filesystem, Shell
                            └── Linux
```

**Android is NOT a provider. Android is the primary OS.**
**Termux is NOT an OS. Termux is a Linux runtime inside Android.**

## Implemented Modules (Sprint 7)

### config/
JSON-based configuration with environment variable overrides (`FLOWCORE__SECTION__KEY`).
Deep-merges `default.json` with `local.json` (if present).

### storage/ ← NEW in Sprint 7
Repository pattern replacing 8+ duplicated inline DB patterns.

- `database.py` — single source of truth for DB path resolution
- `document_repo.py` — document CRUD with sync wrappers
- `memory_repo.py` — memory CRUD wrapping `~/.flowcore/memories.json`

### runtime/
Application lifecycle: start, stop, signal handling. Initialises the database
(SQLAlchemy) and detects platform (Termux/Android/Linux).

### executor/
Async task execution with queue, retry logic, timeout enforcement, semaphore-based
concurrency. Fully standalone.

### scheduler/
APScheduler wrapper for periodic task execution.

### agents/
`BaseAgent` (ABC) + `AgentRegistry`. Every agent implements `run()` and
`health_check()`. Passport validation will be added in Sprint 10.

### api/
FastAPI REST API bound to `127.0.0.1:8080`. Currently uses in-memory store;
will be connected to the Execution Engine in Sprint 8.

### scripts/
`audit.py` — security and compatibility checker.
`helpers.py` — platform utilities.

## Planned Modules (Sprints 8-11)

| Module            | Sprint | Purpose                              |
|-------------------|--------|--------------------------------------|
| `context/`        | 8      | Context Engine + flowcore.context.json|
| `bridges/`        | 9      | AndroidBridge, TermuxBridge, Linux    |
| `capability/`     | 9      | CapabilityRegistry + Provider Resolver|
| `passport/`       | 10     | PassportGenerator + Validator         |
| `bridges/docker`  | 11     | Docker runtime support                |
| `mcp/`            | 11     | FlowCore as MCP Server                |

## Contracts

Three JSON contracts define the FlowCore protocol:

| Contract                     | Produced by      | Sprint |
|------------------------------|------------------|--------|
| `flowcore.context.json`      | Context Engine   | 8      |
| `flowcore.runtime.json`      | Runtime Manager  | 9      |
| `flowcore.capabilities.json` | Capability Reg.  | 10     |

## Security Model

| Layer   | Control                                          |
|---------|--------------------------------------------------|
| Network | API binds to `127.0.0.1` — not network-exposed   |
| Privilege | No root/sudo — user space only                 |
| Secrets | All credentials via environment variables        |
| Code    | No `os.system()`, no shell injection             |
| Agents  | No agent executes without valid Passport (Sprint 10) |
| Bridges | Shell commands encapsulated — never seen by LLM  |

## Data Flow (Current)

```
User/CLI ──> flowcore.py ──> StorageLayer ──> SQLite / JSON
                        └──> Ollama HTTP  ──> AI Response
                        └──> cmd_serve    ──> FastAPI ──> in-memory
```

## Data Flow (Target — Sprint 11)

```
User/MCP/CLI
    ──> Intent Layer
    ──> Agent (with Passport)
    ──> Execution Engine
    ──> Capability Registry ──> Bridge ──> OS
    ──> Storage Layer       ──> SQLite
    ──> Context Engine      ──> flowcore.context.json
```

## Resource Usage

| Resource | Target  |
|----------|---------|
| RAM      | ~50–100 MB idle |
| Disk     | ~10 MB (core only) |
| CPU      | Minimal (event-driven) |
| Battery  | Low (batch scheduling, no polling) |
