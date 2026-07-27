#!/usr/bin/env bash
set -euo pipefail

INSTALL_LOG="logs/install.log"
PYTHON_CMD="python3"

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

log_info "Installing FastAPI stack..."
if ! $PYTHON_CMD -m pip install -r requirements-api.txt --quiet 2>/dev/null; then
    log_error "API installation failed"
    echo ""
    echo "If pydantic-core failed to compile:"
    echo "  • On Termux: Enable TUR and install python-pydantic-core"
    echo "  • On other systems: Ensure build-essential is installed"
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
