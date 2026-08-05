# Release Notes — Sprint 13

Covers commits `2df69b4`..`b367a69` (following Sprint 12's `08deb9e`). Focus: MCP integration, an Ollama pipeline that no longer assumes a fixed local endpoint, and the first usable version of the Web UI (Chat + Settings).

## Added

### MCP server
- `mcp_server.py` — a stdio MCP server (`python3 flowcore.py mcp`) exposing 12 tools: `flowcore_remember`, `flowcore_recall`, `flowcore_memories`, `flowcore_docs`, `flowcore_show`, `flowcore_import_markdown`, `flowcore_search`, `flowcore_daily_summary`, `flowcore_stats`, `flowcore_note`, `flowcore_todo`, `flowcore_agenda`, `flowcore_ask`. Lets MCP clients (e.g. Claude Code) call FlowCore directly instead of shelling out to the CLI.

### Ollama auto-discovery and generation pipeline (`runtime/ollama.py`, new module)
- `discover_ollama_endpoint()` / `discover_default_model()` — replace the previous hardcoded `127.0.0.1:11434` + `"llama2"` assumption. `FLOWCORE_OLLAMA`/`FLOWCORE_MODEL` env vars always win if set; otherwise probes `127.0.0.1`, `host.docker.internal`, and the default network gateway (covers WSL2→Windows and Termux/LAN cases) against `/api/tags`.
- Auto-picked models are chosen by a priority list (`gpt-oss, glm, qwen, deepseek, llama, mistral, phi, gemma`) and cloud-only (`:cloud`-tagged / `remote_host`) models are excluded from auto-pick — they require a paid subscription and would otherwise fail unpredictably.
- `generate()` — checks `/api/ps`, warms up the model if not already loaded (no-prompt `/api/generate` trick + poll), configurable timeout (`FLOWCORE_OLLAMA_TIMEOUT`, default 180s, previously a fixed 30s), and classifies failures into `OllamaUnreachableError`, `OllamaModelNotInstalledError`, `OllamaSubscriptionRequiredError`, `OllamaModelLoadTimeoutError` instead of one generic failure.
- `flowcore.py`'s `cmd_ask`/`cmd_ping`/`cmd_models`/`cmd_stats`/`cmd_doctor` and `mcp_server.py`'s `flowcore_ask` all share this single pipeline — no duplicated Ollama-calling logic.

### Benchmark framework
- `scripts/benchmark_models.py` — auto-detects every installed non-cloud model on the discovered Ollama endpoint and runs a 5-category suite (reasoning, coding, RAG grounding, agent/tool-use structured output, Portuguese) with automated pass/fail checks, timing, and VRAM usage. Produces a comparison table and per-category "fastest passing model" recommendation.
- Real run across 5 models (`glm4:9b`, `qwen2.5:14b`, `qwen3:8b`, `qwen3:4b`, `qwen2.5:7b`) on the Windows Ollama install recommends **`qwen2.5:7b`** as the default — fastest on every category and the only model with zero timeouts across all 5.

### Web UI — Chat and Settings (first usable version)
- `POST /api/ask` — RAG-grounded chat endpoint, reuses the `runtime/ollama.py` pipeline directly, offloaded via `asyncio.to_thread` so long generations don't block other requests.
- `GET /api/settings` — surfaces FlowCore version, platform, and the currently active Ollama endpoint/model.
- New "Chat" and "Config" tabs in `web/index.html`, reusing the existing card/input-row component vocabulary — no new visual language introduced.
- Verified end-to-end through a real headless-browser session (not just curl): page load, tab navigation, a full 3-prompt chat exchange (greeting, reasoning, RAG-grounded), zero console/network errors.

## Fixed

- **`asyncio.run()` crash inside an already-running event loop** — found and fixed at two independent call sites this sprint: `mcp_server.py`'s document tools (`flowcore_docs`, `flowcore_show`, `flowcore_search`, etc.) and `api/router.py`'s `/api/notes` and `/api/search`. Root cause: `DocumentRepository`'s `*_sync()` wrapper methods call `asyncio.run()` internally, which breaks inside FastAPI's/FastMCP's own event loop. Fixed by awaiting the native async methods directly at each call site — the `*_sync()` wrappers themselves are unchanged and would still break any *other* future async caller (flagged, not fixed — see Known Issues).
- **Model-load timeout misclassified as "unreachable"** — the warm-up call's own socket read-timeout was raising `OllamaUnreachableError` even though `/api/ps` had just confirmed Ollama was reachable. Fixed by treating a bare `TimeoutError` during warm-up as "still loading" (fall through to the `/api/ps` poll loop) rather than an immediate failure.
- **Cloud model masked as load-timeout** — `glm-5.2:cloud`'s no-prompt warm-up returned `200` without ever triggering the real subscription check, so it never appeared in `/api/ps` and always timed out instead of surfacing the actual `403`. Fixed by skipping the load-wait mechanism entirely for cloud-tagged models.
- **Windows↔WSL2 Ollama reachability** — Windows' Ollama was bound to `127.0.0.1:11434` only, unreachable from WSL2 by design. Resolved by setting `OLLAMA_HOST=0.0.0.0:11434` on the Windows side and restarting the service; no FlowCore code change.
- **Port 8080 conflict** — an unrelated pre-existing Docker service (`evolution-api`) occupies port 8080 on the dev machine. Resolved via `config/local.json` (the config loader's existing local-override layer) rather than touching FlowCore's default port or the unrelated Docker stack.

## Documentation / repo hygiene (Release Candidate review)

- Repo-wide dead-code and unused-import cleanup across 24 files — see commit `b367a69` for the full list of what was removed and, importantly, what was deliberately **not** touched and why (availability-probe imports, an orphaned-but-intentional `agents/` module, an unwired `started_at` field, per-platform capability-adapter divergence that looks like duplication but isn't).
- `.gitignore` fixed to cover `config/local.json` (was missing despite being exactly the per-machine override pattern `.env.local` already follows).
- Full regression: all 136 existing tests pass (before and after cleanup), every API endpoint verified live (including write/delete round trips), every Web UI page verified via a real headless-browser session with zero console/network errors.

## Known issues (not fixed this sprint — flagged for a deliberate decision, not guessed at)

- **Test isolation**: running `pytest tests/` writes real entries into the live `~/.flowcore/memories.json` instead of a temp/mock store. Confirmed twice this sprint; cleaned up manually each time.
- **`storage/document_repo.py`'s `*_sync()` methods** are still broken for any caller running inside an event loop — every *known* call site has been fixed, but the root cause in the wrapper methods themselves remains.
- **`api/router.py`'s execution-submit endpoint**: `now = time.time()` is computed but never assigned to `started_at` (stays `None`). Looks like a real one-line bug in the flows/executions stub, not simple dead code.
- **FastAPI and MCP are fully separate, non-communicating processes** — they share on-disk files (SQLite, memories JSON) but duplicate logic independently (e.g. note-kind labels exist once in each). No unification exists yet; see `ARCHITECTURE.md`.
- **`agents/` module** (`BaseAgent`, `AgentRegistry`) has zero references anywhere in the codebase — appears to be forward-looking scaffolding, not wired to anything yet.
- **`PassportValidator`/`ValidationResult`** are fully tested but not called by any running endpoint (`/api/passport` only uses `PassportGenerator`).
- **No CI/CD** — `ROADMAP.md` previously claimed this was done; it never existed (`.github/workflows/` has no files, confirmed via full git history, not just the current tree).
