# DARIUS OSS — Technical Architecture Specification
**Document Version:** 1.0.0  
**Date:** 2026-09-08  
**Architecture Style:** Hexagonal (Ports and Adapters) + Event-Driven Asynchronous Pipeline

---

## 1. Architectural Principles

1. **Strict Hexagonal Separation (Ports & Adapters):**
   * Core domain logic never depends on external protocols (HTTP, Telegram, Ollama, WhatsApp, SQLite).
   * External systems communicate with the core exclusively via typed Protocols (`darius/interfaces/`).
2. **Asynchronous Non-Blocking Execution:**
   * No network I/O, heavy computation, or external notification may block the main server event loop.
   * Jobs longer than 500ms must run in background workers (`darius/jobs/`).
3. **Graceful Degradation & Resilience:**
   * External service failures (Ollama offline, Telegram rate limits, Yahoo Finance timeouts) must degrade gracefully with automatic fallback and transparent telemetry.
4. **Zero State Collisions with Core Runtime:**
   * Core execution primitives (`Task`, `State`, `Agent Core`) are strictly maintained by Jules. Systems Engineering provides supporting infrastructure and adapters.

---

## 2. High-Level System Architecture

```
                               ┌──────────────────────────┐
                               │   Presentation Layer     │
                               │  FastAPI | CLI | Web UI  │
                               └────────────┬─────────────┘
                                            │
                               ┌────────────▼─────────────┐
                               │    Service Layer (API)   │
                               │    api/dashboard_routes  │
                               └────────────┬─────────────┘
                                            │
               ┌────────────────────────────┼────────────────────────────┐
               │                            │                            │
 ┌─────────────▼──────────────┐ ┌───────────▼────────────┐ ┌─────────────▼──────────────┐
 │    Core Runtime (Jules)    │ │   Autonomous Agents    │ │    Async Job Dispatcher    │
 │ Task | State | Agent Core  │ │  Orchestrator | Loops  │ │      darius/jobs/          │
 └─────────────┬──────────────┘ └───────────┬────────────┘ └─────────────┬──────────────┘
               │                            │                            │
═══════════════╪════════════════════════════╪════════════════════════════╪══════════════════ (Boundary)
               │          PORTS & ADAPTERS INTERFACES (darius/interfaces/)
               ├────────────────────────────┼────────────────────────────┤
 ┌─────────────▼──────────────┐ ┌───────────▼────────────┐ ┌─────────────▼──────────────┐
 │        LLM Adapter         │ │      Tool Adapter      │ │    Notification Adapter    │
 │ (Ollama/DeepSeek/OpenRouter│ │ (Capability / Sandboxed│ │ (Telegram, WhatsApp, Email)│
 └────────────────────────────┘ └────────────────────────┘ └────────────────────────────┘
 ┌────────────────────────────┐ ┌────────────────────────┐ ┌────────────────────────────┐
 │       Memory Adapter       │ │     Skill Adapter      │ │        MCP Adapter         │
 │ (Working, Episodic, Vector)│ │ (Manifest, Prompt Inj) │ │ (FastMCP Bidirectional)    │
 └────────────────────────────┘ └────────────────────────┘ └────────────────────────────┘
```

---

## 3. Interfaces & Contracts Specification (`darius/interfaces/`)

### 3.1. LLM Adapter (`darius/interfaces/llm.py`)
```python
class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None
    tool_calls: list[dict[str, Any]] | None = None

class LLMResponse(BaseModel):
    content: str
    model: str
    provider: str
    usage: dict[str, int]
    latency_ms: int
    finish_reason: str | None = None

class LLMAdapter(Protocol):
    async def generate(self, messages: list[LLMMessage], **kwargs) -> LLMResponse: ...
    async def stream(self, messages: list[LLMMessage], **kwargs) -> AsyncIterator[str]: ...
    async def health(self) -> dict[str, Any]: ...
```

### 3.2. Tool Adapter (`darius/interfaces/tools.py`)
```python
class ToolParameter(BaseModel):
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None

class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: list[ToolParameter]
    permission_level: Literal["read", "write", "execute", "critical"] = "read"

class ToolExecutionResult(BaseModel):
    success: bool
    output: Any
    error: str | None = None
    execution_ms: int = 0

class ToolAdapter(Protocol):
    @property
    def definition(self) -> ToolDefinition: ...
    async def execute(self, params: dict[str, Any], context: dict[str, Any] | None = None) -> ToolExecutionResult: ...
```

### 3.3. Notification Adapter (`darius/interfaces/notifications.py`)
```python
class NotificationMessage(BaseModel):
    title: str
    body: str
    level: Literal["INFO", "WARNING", "CRITICAL"] = "INFO"
    recipient: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class NotificationDeliveryResult(BaseModel):
    success: bool
    channel: str
    delivered_at: float
    error: str | None = None

class NotificationChannelAdapter(Protocol):
    @property
    def channel_name(self) -> str: ...
    async def send(self, message: NotificationMessage) -> NotificationDeliveryResult: ...
    async def is_available(self) -> bool: ...
```

### 3.4. Memory Adapter (`darius/interfaces/memory.py`)
```python
class MemoryEntry(BaseModel):
    id: str
    content: str
    category: Literal["working", "episodic", "semantic"]
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: float

class MemoryAdapter(Protocol):
    async def store(self, entry: MemoryEntry) -> bool: ...
    async def retrieve(self, query: str, limit: int = 5, **kwargs) -> list[MemoryEntry]: ...
    async def clear_working_memory(self, session_id: str) -> None: ...
```

### 3.5. Skill Adapter (`darius/interfaces/skills.py`)
```python
class SkillManifest(BaseModel):
    id: str
    name: str
    version: str
    description: str
    system_prompt_snippet: str
    required_tools: list[str]
    enabled: bool = True

class SkillAdapter(Protocol):
    @property
    def manifest(self) -> SkillManifest: ...
    async def activate(self, context: dict[str, Any]) -> bool: ...
```

---

## 4. Asynchronous Job & Dispatcher Architecture (`darius/jobs/`)

To solve the 45-second cold start and prevent network timeouts:
1. **Background Job Queue:** In-process asyncio non-blocking queue.
2. **Prioritization:** `CRITICAL` jobs run ahead of `BATCH` and `MONITORING` jobs.
3. **Execution Isolation:** Worker timeouts, circuit breakers, and automatic retries with exponential backoff.
4. **Cache Materialization:** Precomputes heavy operations (Market, Macro, Compliance, Priorities) in the background and writes snapshot summaries to SQLite/in-memory cache for instantaneous REST response (< 20ms).
