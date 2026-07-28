# FlowCore

> Lightweight workflow automation engine for Android / Termux.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Termux%20%7C%20Linux%20%7C%20macOS-orange.svg)](#)

---

## What is FlowCore?

FlowCore is a **lightweight, Python-based workflow automation engine** designed to run natively on **Android via Termux**. It provides:

- **Task scheduling** — run tasks on intervals (cron-like)
- **Flow execution** — define and execute named workflows
- **Agent framework** — pluggable agents for custom logic
- **Local API** — REST API bound to localhost for programmatic access
- **Self-healing** — built-in repair, optimize, and update tools

**Zero external dependencies** beyond Python packages. No Docker, no PostgreSQL, no Redis required. Uses SQLite for persistence.

---

## Architecture

```
FlowCore/
├── install.sh              # One-line installer
├── flowcore.py             # Main entry point (serve, run, health, version)
├── daemon.py               # Background daemon manager
├── validate_android.sh     # Android compatibility validator
├── doctor.sh               # Diagnostic tool
├── optimize.sh             # Performance optimizer
├── benchmark.sh            # Benchmark tool
├── update.sh               # Safe update script
├── repair.sh               # Self-repair script
├── uninstall.sh            # Clean removal
├── requirements.txt        # Python dependencies
├── config/
│   ├── default.yml         # Default configuration (version-controlled)
│   └── local.yml           # Local overrides (gitignored)
├── runtime/                # Application lifecycle
│   └── core.py
├── executor/               # Task execution engine
│   └── engine.py
├── scheduler/              # Periodic task scheduling
│   └── service.py
├── api/                    # REST API (localhost only)
│   └── router.py
├── agents/                 # Agent framework
│   ├── base.py
│   └── health_agent.py
├── scripts/                # Helper utilities
│   ├── helpers.py
│   └── audit.py
├── logs/                   # Log files
├── backups/                # Backup directory
└── data/                   # SQLite database
```

---

## Quick Start

### Installation (Termux)

```bash
pkg install python git
git clone https://github.com/prdariomarques-ship-it/FlowCore.git
cd FlowCore
bash install.sh
```

### Start the API

```bash
python3 flowcore.py serve
```

### Run as daemon

```bash
python3 daemon.py start     # Start in background
python3 daemon.py status    # Check status
python3 daemon.py stop      # Stop daemon
python3 daemon.py restart   # Restart daemon
```

### Health check

```bash
python3 flowcore.py health
# or
curl http://127.0.0.1:8080/api/health
```

---

## Configuration

All configuration lives in `config/default.yml`. Override values in `config/local.yml` (never committed).

### Environment variable overrides

```bash
export FLOWCORE__API__PORT=9090
export FLOWCORE__API__HOST=0.0.0.0
export FLOWCORE__LOGGING__LEVEL=DEBUG
```

### Key settings

| Setting | Default | Description |
|---------|---------|-------------|
| `api.host` | `127.0.0.1` | API bind address |
| `api.port` | `8080` | API port |
| `runtime.max_concurrent_tasks` | `2` | Max parallel tasks (mobile-friendly) |
| `scheduler.timezone` | `America/Sao_Paulo` | Scheduler timezone |
| `security.allow_remote_access` | `false` | Allow remote API access |
| `security.auto_root` | `false` | Auto-elevate privileges (disabled) |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/flows` | List all flows |
| POST | `/api/flows` | Create a flow |
| GET | `/api/flows/{id}` | Get flow details |
| DELETE | `/api/flows/{id}` | Delete a flow |
| GET | `/api/executions` | List executions |
| POST | `/api/executions` | Submit a task |
| GET | `/api/executions/{id}` | Get execution status |

---

## CLI Commands

### Core Commands

| Command | Description |
|---------|-------------|
| `python3 flowcore.py serve` | Start API server (localhost:8080) |
| `python3 flowcore.py run` | Start full app (API + scheduler + agents) |
| `python3 flowcore.py health` | Health check |
| `python3 flowcore.py version` | Print version info |
| `python3 flowcore.py selftest` | Validate installation |
| `python3 flowcore.py chat` | Interactive chat session |

### Memory & Knowledge

| Command | Description |
|---------|-------------|
| `python3 flowcore.py remember "text"` | Save memory with #hashtags |
| `python3 flowcore.py recall "keyword"` | Search memories (substring) |
| `python3 flowcore.py memories` | List all memories |

### Document Management

| Command | Description |
|---------|-------------|
| `python3 flowcore.py import file.md` | Import Markdown (title from first `# `) |
| `python3 flowcore.py docs` | List documents |
| `python3 flowcore.py show 1` | Display document by ID |

### Task Management

| Command | Description |
|---------|-------------|
| `python3 flowcore.py note "text"` | Add a note |
| `python3 flowcore.py todo "task"` | Add a todo item |
| `python3 flowcore.py agenda "event"` | Add to agenda |

### AI & Ollama

| Command | Description |
|---------|-------------|
| `python3 flowcore.py ask "question"` | RAG query with Ollama |
| `python3 flowcore.py ping` | Test Ollama connection |
| `python3 flowcore.py models` | List available Ollama models |

### System

| Command | Description |
|---------|-------------|
| `python3 flowcore.py stats` | Show statistics (memories, docs, model, version) |
| `python3 flowcore.py doctor` | System health check (Python, SQLite, Config, Ollama, API, Scheduler) |
| `python3 flowcore.py demo` | Interactive demo walkthrough |

### Legacy Shell Scripts

| Command | Description |
|---------|-------------|
| `bash validate_android.sh` | Validate Android compatibility |
| `bash optimize.sh` | Optimize performance |
| `bash benchmark.sh` | Run benchmarks |
| `bash update.sh` | Update FlowCore |
| `bash repair.sh` | Self-repair |
| `bash uninstall.sh` | Remove FlowCore |
| `bash uninstall.sh --purge` | Remove everything (data included) |

---

## Usage Examples

### Memory System

```bash
# Save memories with automatic #hashtag extraction
python3 flowcore.py remember "Working on FlowCore #project #android"

# Recall by keyword (substring search, case-insensitive)
python3 flowcore.py recall android
python3 flowcore.py recall FlowCore

# List all memories
python3 flowcore.py memories
```

### Document Management (RAG)

```bash
# Import Markdown files (auto-extracts title from first #)
python3 flowcore.py import my_notes.md
python3 flowcore.py import documentation.md

# List all documents
python3 flowcore.py docs

# Show specific document
python3 flowcore.py show 1
```

### AI with Ollama

```bash
# Ask questions with document context
python3 flowcore.py ask "How do I install FlowCore?"

# Test Ollama connection
python3 flowcore.py ping

# List available models
python3 flowcore.py models

# Set model and host via environment
export FLOWCORE_MODEL=qwen3:8b
export FLOWCORE_OLLAMA=http://127.0.0.1:11434
python3 flowcore.py ask "What is FlowCore?"
```

### System Status

```bash
# Show statistics
python3 flowcore.py stats

# Full system health check
python3 flowcore.py doctor

# Interactive demo
python3 flowcore.py demo
```

---

## Troubleshooting

### "python3 not found"

```bash
pkg install python          # Termux
apt install python3         # Ubuntu/Debian
brew install python         # macOS
```

### "Module not found"

```bash
python3 -m pip install -r requirements.txt
```

### Daemon won't start

```bash
bash repair.sh              # Auto-fix common issues
bash doctor.sh              # Check diagnostics
```

### Database errors

```bash
rm data/flowcore.db         # Reset database (data will be lost)
python3 flowcore.py serve   # Auto-recreates tables
```

### API not accessible from another device

By design, the API binds to `127.0.0.1` only. To expose it:

```yaml
# config/local.yml
api:
  host: "0.0.0.0"
```

**Warning:** This exposes the API to the network. Only do this on trusted networks.

---

## Security

FlowCore is designed with security in mind:

- **API binds to localhost** — not accessible from the network by default
- **No root/sudo required** — runs entirely in user space
- **No hardcoded credentials** — all secrets via environment variables
- **No dangerous system calls** — no `os.system()` or `subprocess` with user input
- **auto_root disabled** — never escalates privileges automatically

Run `python3 scripts/audit.py` to verify security posture.

---

## Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| Python | 3.11 | 3.12+ |
| RAM | 512 MB | 1 GB |
| Disk | 50 MB | 100 MB |
| OS | Android 12+ / Linux / macOS | Android 15 / Linux |

### Termux packages

```
python, git, openssl
```

---

## License

MIT. See [LICENSE](LICENSE) for details.
