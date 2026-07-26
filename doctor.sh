#!/usr/bin/env bash
# ============================================================================
# FlowCore — Doctor (diagnostic tool)
# ============================================================================
# Provides detailed diagnostics for troubleshooting.
# Usage: bash doctor.sh
# ============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}=============================================="
echo "  FlowCore Doctor — Diagnostics"
echo "==============================================${NC}"
echo ""

echo -e "${CYAN}System Information${NC}"
echo "  Hostname:  $(hostname 2>/dev/null || echo 'unknown')"
echo "  OS:        $(uname -a 2>/dev/null || echo 'unknown')"
echo "  Shell:     $SHELL"
echo "  User:      $(whoami 2>/dev/null || echo 'unknown')"
echo ""

echo -e "${CYAN}Python Environment${NC}"
if command -v python3 &>/dev/null; then
    echo "  Python:    $(python3 --version 2>&1)"
    echo "  Location:  $(which python3)"
    echo "  Packages:  $(python3 -m pip list 2>/dev/null | wc -l | tr -d ' ') installed"
else
    echo -e "  ${RED}Python3 not found${NC}"
fi
echo ""

echo -e "${CYAN}FlowCore Dependencies${NC}"
python3 -c "
import importlib
deps = ['fastapi', 'uvicorn', 'loguru', 'pydantic', 'yaml', 'aiosqlite', 'sqlalchemy', 'httpx', 'apscheduler']
for dep in deps:
    try:
        mod = importlib.import_module(dep)
        ver = getattr(mod, '__version__', 'unknown')
        print(f'  {dep:20s} {ver}')
    except ImportError:
        print(f'  {dep:20s} MISSING')
" 2>/dev/null
echo ""

echo -e "${CYAN}Configuration${NC}"
python3 -c "
from config.loader import get_config
cfg = get_config()
print(f'  App:       {cfg[\"app\"][\"name\"]} v{cfg[\"app\"][\"version\"]}')
print(f'  API Host:  {cfg[\"api\"][\"host\"]}')
print(f'  API Port:  {cfg[\"api\"][\"port\"]}')
print(f'  Database:  {cfg[\"database\"][\"url\"][:50]}...')
print(f'  Log Level: {cfg[\"logging\"][\"level\"]}')
print(f'  Debug:     {cfg[\"app\"][\"debug\"]}')
" 2>/dev/null
echo ""

echo -e "${CYAN}Daemon Status${NC}"
PID_FILE="logs/flowcore.pid"
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "  Running:   YES (PID $PID)"
    else
        echo -e "  Running:   ${RED}NO${NC} (stale PID file)"
    fi
else
    echo "  Running:   NO"
fi
echo ""

echo -e "${CYAN}Disk Usage${NC}"
echo "  Project:   $(du -sh . 2>/dev/null | cut -f1)"
echo "  Logs:      $(du -sh logs/ 2>/dev/null | cut -f1)"
echo "  Data:      $(du -sh data/ 2>/dev/null | cut -f1)"
echo ""

echo -e "${CYAN}Recent Logs (last 10 lines)${NC}"
if [ -f "logs/flowcore.log" ]; then
    tail -10 logs/flowcore.log 2>/dev/null
else
    echo "  No log file found"
fi
echo ""

echo -e "${CYAN}==============================================${NC}"
echo "  Diagnostics complete"
echo -e "${CYAN}==============================================${NC}"
