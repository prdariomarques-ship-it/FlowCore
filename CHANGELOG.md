# Changelog

All notable changes to FlowCore will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.5.0] — 2026-08-06

Priority directive: architecture and foundations over feature count. Realizes
`ROADMAP.md`'s Version 2.0 ("AI Router + Policy Engine") ahead of its
original sequencing.

### Added

- **LLM Router** (`runtime/llm/`) — the single, permanent abstraction layer
  between FlowCore and any LLM backend. Provider abstraction (`LLMProvider`),
  provider registry, `LocalFirstPolicy` (the Policy Engine — Ollama always
  first, cloud only ever opt-in per request via `metadata["allow_cloud"]`,
  never a silent fallback), metrics/cache/budget interfaces (each with a
  real, working default implementation, not just a stub), retry-then-
  fallback orchestration in `LLMRouter`. Two shipped providers:
  `OllamaProvider` (wraps the existing local integration) and
  `OpenRouterProvider` (the default cloud backend — one OpenAI-compatible
  API in front of GPT/Claude/Gemini/DeepSeek/many others, so no
  provider class per cloud vendor was needed). `GET /api/llm/status`,
  `flowcore.py llm status`, `flowcore_llm_status` MCP tool.
  `docs/LLM_ROUTER_ARCHITECTURE.md` — full design + "adding a new
  provider" guide.

### Changed

- `runtime/narrative/` (Sprint 25) migrated off `runtime/ollama.py`
  directly onto an injected `LLMRouter` — the one SCPX-pipeline LLM
  consumer, now provider-agnostic and structurally incapable of reaching
  a cloud provider without a deliberate code change.

## [1.4.0] — 2026-08-06

Sprint 25.

### Added

- **SCPX Narrative Engine** (`runtime/narrative/`, Layer 6) — translates the
  Decision Report (Layer 5) into natural-language prose via the existing
  local Ollama integration. The only layer in the whole SCPX pipeline allowed
  to call an LLM, and strictly as presentation: it narrates an already-final
  decision, never influences one. Degrades to a deterministic, LLM-free
  fallback narrative (built from the same reason chains) if Ollama is
  unavailable — the feature always returns something usable, never errors.
  `GET /api/portfolios/{id}/narrative?shelf=...`, `flowcore.py portfolio
  narrative`, `flowcore_portfolio_narrative` MCP tool, a "Narrativa" card
  in the Web UI's Portfólio tab (manual "Gerar narrativa" trigger, same
  click-to-generate pattern as the Chat tab).

## [1.3.0] — 2026-08-06

Sprint 24. Note: this entry follows directly from [1.2.0] below in this file,
but the codebase moved through Sprints 14–23 in between without corresponding
CHANGELOG entries — see `git log` and `ARCHITECTURE.md`'s new "SCPX Wealth
Copilot pipeline" section for that history. Catching up from here forward,
per standing instruction to update this file at the end of every sprint.

### Added

- **SCPX Decision Engine** (`runtime/decision/`, Layer 5 of the SCPX pipeline) — turns
  the generic recommendations from the Recommendation Engine into an ordered,
  explainable Decision Queue: priority ranking (`priority.py`, a documented
  5-term weighted formula), urgency classification (`urgency.py`), confidence
  scaled by materiality (`confidence.py`), an 8-question reason chain per
  decision (`reason_chain.py`), and an 8-sub-score Decision Readiness Score
  (`portfolio_score.py` — concentration, diversification, inflation hedge,
  currency protection, duration, liquidity, macro alignment, protection).
  Deterministic only, no LLM. `GET /api/portfolios/{id}/decision[/queue|/score]`,
  `GET /api/portfolios/{id}/reason-chain`, `flowcore.py portfolio
  decision|queue|score|explain`, 4 MCP tools. Web UI: 3 new cards in the
  existing Portfólio tab (Decisão, Score do Portfólio, Fila de Decisões).
- **Architecture correction mid-sprint**: the Impact Engine had drifted into
  holding product knowledge (hardcoded ETF tickers). Split cleanly into
  Layer 2 (Portfolio Impact, category-only), Layer 3 (Recommendation, generic
  `action_key`), and a new Layer 4 (`runtime/product_mapping/`) — the only
  layer allowed to know concrete products, entirely via swappable
  `config/product_shelves/*.json` (`us_etf`, `br_renda_fixa` shipped as
  reference shelves).

## [1.2.0] — 2026-08-05

Sprint 13. Full details in `RELEASE_NOTES.md`. Note: this entry follows directly
from [1.1.0] below in this file, but the codebase moved through Sprints 5–12
in between without corresponding CHANGELOG entries — see `git log` for that
history.

### Added

- MCP stdio server (`flowcore.py mcp` / `mcp_server.py`) — 12 tools for external MCP clients
- Ollama endpoint/model auto-discovery (`runtime/ollama.py`), replacing the previous hardcoded `127.0.0.1:11434` + `llama2` assumption
- Generation pipeline: warm-up, `/api/ps` polling, configurable timeout, 4 classified error types
- Model benchmark framework (`scripts/benchmark_models.py`)
- Web UI: Chat page (`POST /api/ask`) and Settings page (`GET /api/settings`) — first usable Web UI version

### Fixed

- `asyncio.run()` crash inside an already-running event loop, at two independent call sites (`mcp_server.py` document tools, `api/router.py`'s `/api/notes` and `/api/search`)
- Model-load timeout misclassified as "unreachable"
- Cloud-only Ollama models masked as load-timeout instead of surfacing the real subscription error
- Windows↔WSL2 Ollama reachability (environment fix, not code)

### Changed

- Repo-wide dead-code and unused-import cleanup (24 files, no logic changes)
- `ARCHITECTURE.md` and `ROADMAP.md` rewritten to match current, verified reality (previous versions described aspirational/stale state, including a false "CI/CD: Done" claim)

## [1.1.0] — 2026-07-27

### Added

- Memory system: `remember`, `recall` (substring search), `memories` with JSON persistence
- Document management: `import` Markdown with title extraction, `docs`, `show`
- Task management: `note`, `todo`, `agenda` (SQLite persistence)
- AI integration: `ask` command with RAG (stdlib urllib, no requests)
- Ollama integration: `ping` (connection test), `models` (list), configurable via env vars
- System diagnostics: `doctor` (health check), `stats` (statistics), `demo` (interactive demo)
- Environment variables: `FLOWCORE_MODEL`, `FLOWCORE_OLLAMA` for customization
- Graceful error handling: no tracebacks, user-friendly messages (português)

### Fixed

- `recall` now searches by substring in memory text, not just hashtags
- `ask` uses stdlib `urllib.request` (zero external dependencies)
- All commands handle missing Ollama gracefully
- Selftest covers all commands with proper isolation

### Changed

- Unified single branch: `develop` merged into `main`, only `main` used
- `import` extracts first `# ` as title, shows metadata (linhas/caracteres/ID)
- RAG context limited to top 5 documents, 300 chars each

---

## [1.0.0] — 2026-07-27

### Added

- Core architecture: config, runtime, executor, scheduler, API, agents
- `flowcore.py` CLI with commands: serve, run, health, version, selftest
- `daemon.py` background process manager (start/stop/status/restart)
- `install.sh` one-line installer for Termux / Linux / macOS
- `validate_android.sh` Android compatibility validator
- `doctor.sh` diagnostic tool
- `optimize.sh` performance optimizer
- `benchmark.sh` performance benchmark
- `update.sh` safe update script (preserves data and config)
- `repair.sh` self-repair script
- `uninstall.sh` clean removal script
- REST API with FastAPI: health, flows, executions endpoints
- Agent framework with base class and health agent
- Task execution engine with retry, timeout, and result tracking
- Periodic task scheduler (APScheduler)
- SQLite persistence (aiosqlite)
- YAML configuration with environment variable overrides
- Security audit tool (`scripts/audit.py`)
- GitHub Actions: CI (lint, test), Release, Security
- PR template, issue templates (bug report, feature request)
- CODEOWNERS, CONTRIBUTING.md, SECURITY.md
- INSTALL_TERMUX.md for Android installation guide
- MIT License

### Security

- API binds to `127.0.0.1` by default
- No root/sudo dependencies
- No hardcoded credentials
- No dangerous system calls
- `auto_root` disabled by default

### Compatibility

- Termux (Android 12+)
- Python 3.11–3.13
- Linux / macOS
- All dependencies pure-Python (no C extensions)
