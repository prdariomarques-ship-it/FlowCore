#!/usr/bin/env bash
# ============================================================================
# FlowCore — Uninstall Script
# ============================================================================
# Removes FlowCore from the system.
# By default, preserves data and config.
# Use --purge to remove everything.
# ============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PURGE=false

for arg in "$@"; do
    if [ "$arg" = "--purge" ]; then
        PURGE=true
    fi
done

echo "=============================================="
echo "  FlowCore Uninstall"
echo "=============================================="
echo ""

if [ "$PURGE" = true ]; then
    echo -e "${RED}PURGE MODE: This will delete ALL data, config, and backups.${NC}"
else
    echo "Standard mode: data and config will be preserved."
    echo "Use --purge to remove everything."
fi
echo ""

# ── Stop daemon ──────────────────────────────────────────────────────────
echo -e "${YELLOW}[1/4]${NC} Stopping daemon..."
PID_FILE="logs/flowcore.pid"
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" 2>/dev/null || true
        sleep 2
        kill -9 "$PID" 2>/dev/null || true
        echo "  Daemon stopped (PID $PID)"
    else
        echo "  Daemon was not running"
    fi
    rm -f "$PID_FILE"
else
    echo "  No daemon PID found"
fi

# ── Remove Python packages ───────────────────────────────────────────────
echo -e "${YELLOW}[2/4]${NC} Removing Python packages..."
python3 -m pip uninstall -y fastapi uvicorn loguru pydantic pydantic-settings httpx aiosqlite sqlalchemy apscheduler python-dotenv pyyaml 2>/dev/null || true
echo "  Done"

# ── Remove project files ─────────────────────────────────────────────────
echo -e "${YELLOW}[3/4]${NC} Removing project files..."
if [ "$PURGE" = true ]; then
    # Remove everything in parent directory
    PARENT_DIR=$(dirname "$(pwd)")
    DIR_NAME=$(basename "$(pwd)")
    rm -rf "$PARENT_DIR/$DIR_NAME"
    echo "  Removed: $PARENT_DIR/$DIR_NAME"
else
    # Remove only code, keep data/config/backups
    rm -rf __pycache__ logs/*.log
    find . -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    echo "  Removed: caches and logs"
    echo "  Preserved: data/, config/, backups/"
fi

# ── Done ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${YELLOW}[4/4]${NC} Uninstall complete"
echo "=============================================="

if [ "$PURGE" = true ]; then
    echo -e "${RED}All FlowCore data has been removed.${NC}"
else
    echo -e "${GREEN}FlowCore code removed. Data preserved.${NC}"
    echo "To fully remove, run: bash uninstall.sh --purge"
fi
