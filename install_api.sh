#!/usr/bin/env bash
set -euo pipefail
INSTALL_LOG="logs/install.log"
PYTHON_CMD="python3"
IS_TERMUX=${PREFIX:-}
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'
mkdir -p logs
exec > >(tee -a "$INSTALL_LOG") 2>&1
log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║   FlowCore v1.0.1 — API Installer              ║${NC}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
if [ -n "$IS_TERMUX" ]; then
    log_info "Platform: Termux/Android detected"
    log_info "Installing API dependencies from PyPI..."
    log_warn "Note: pydantic-core requires Rust compilation on some Termux setups."
    log_warn "If installation fails, try: pkg install rust || use pre-built wheels"
fi
log_info "Installing FastAPI stack..."
if ! $PYTHON_CMD -m pip install -r requirements-api.txt --quiet 2>/dev/null; then
    log_error "API installation failed"
    echo ""
    echo "Possible solutions:"
    echo "  1. Upgrade pip: python3 -m pip install --upgrade pip"
    echo "  2. On Termux: ensure build tools are available"
    echo "  3. Try installing individual packages one at a time"
    exit 1
fi
log_info "API stack installed"
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║      API Installation Complete!                ║${NC}"
echo -e "${GREEN}${BOLD}╠══════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}${BOLD}║  FastAPI Stack (optional)                      ║${NC}"
echo -e "${GREEN}${BOLD}║  Status: API Ready                             ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo "Start API:  python3 flowcore.py serve"
echo "Full app:   python3 flowcore.py run"
echo ""
