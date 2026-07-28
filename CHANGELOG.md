# Changelog

All notable changes to FlowCore will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

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
