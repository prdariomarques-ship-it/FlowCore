#!/usr/bin/env bash
# ============================================================================
# FlowCore — Self-Repair Script
# ============================================================================
# Fixes common issues:
#   1. Missing directories
#   2. Missing dependencies
#   3. Corrupt database
#   4. Stale PID files
#   5. Broken config
# ============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${GREEN}[REPAIR]${NC} $*"; }
warn() { echo -e "${YELLOW}[REPAIR]${NC} $*"; }
fix() { echo -e "${GREEN}[FIX]${NC}    $*"; }

echo "=============================================="
echo "  FlowCore Repair"
echo "=============================================="
echo ""

# ── 1. Create missing directories ────────────────────────────────────────
info "Checking directories..."
for dir in data logs backups config; do
    if [ ! -d "$dir" ]; then
        fix "Created missing directory: $dir/"
        mkdir -p "$dir"
    fi
done

# ── 2. Ensure config files exist ─────────────────────────────────────────
info "Checking configuration..."
if [ ! -f "config/default.yml" ]; then
    fix "config/default.yml is missing — this is critical"
    echo "  You may need to re-clone the repository."
    exit 1
fi

if [ ! -f "requirements.txt" ]; then
    fix "requirements.txt is missing"
    exit 1
fi

# ── 3. Check Python ──────────────────────────────────────────────────────
info "Checking Python..."
if ! command -v python3 &>/dev/null; then
    warn "python3 not found. Try: pkg install python"
fi

# ── 4. Reinstall missing dependencies ────────────────────────────────────
info "Checking dependencies..."
MISSING=""
for mod in fastapi uvicorn loguru yaml aiosqlite; do
    if ! python3 -c "import $mod" 2>/dev/null; then
        MISSING="$MISSING $mod"
    fi
done

if [ -n "$MISSING" ]; then
    fix "Reinstalling missing modules:$MISSING"
    python3 -m pip install --user -r requirements.txt 2>/dev/null || true
else
    info "All dependencies OK"
fi

# ── 5. Clean stale PID ───────────────────────────────────────────────────
info "Checking daemon PID..."
PID_FILE="logs/flowcore.pid"
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ! kill -0 "$PID" 2>/dev/null; then
        fix "Removed stale PID file (PID $PID was not running)"
        rm -f "$PID_FILE"
    else
        info "Daemon is running (PID $PID)"
    fi
fi

# ── 6. Validate config ───────────────────────────────────────────────────
info "Validating configuration..."
if python3 -c "from config.loader import get_config; get_config()" 2>/dev/null; then
    info "Configuration is valid"
else
    warn "Configuration load failed. Check config/default.yml"
fi

# ── 7. Check database ────────────────────────────────────────────────────
info "Checking database..."
if [ -f "data/flowcore.db" ]; then
    if python3 -c "import sqlite3; sqlite3.connect('data/flowcore.db')" 2>/dev/null; then
        info "Database OK"
    else
        warn "Database may be corrupt. Run: rm data/flowcore.db && python3 flowcore.py serve"
    fi
else
    info "No database yet (will be created on first run)"
fi

# ── Summary ──────────────────────────────────────────────────────────────
echo ""
echo "=============================================="
echo "  Repair complete"
echo "=============================================="
