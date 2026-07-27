#!/usr/bin/env bash
set -euo pipefail

MIN_DISK_MB=100
INSTALL_LOG="logs/install.log"
PYTHON_CMD="python3"
ROLLBACK_DIR=".install_backup"

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
log_step()  { echo -e "\n${CYAN}${BOLD}[STEP $1/6]${NC} $2"; }

rollback() {
    log_error "Installation failed. Rolling back..."
    [ -d "$ROLLBACK_DIR" ] && rm -rf data backups logs 2>/dev/null || true
    [ -f "$ROLLBACK_DIR/pip.txt" ] && rm -rf "$ROLLBACK_DIR" || true
    exit 1
}

trap rollback ERR

echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║   FlowCore v1.0.1 — Core Installer             ║${NC}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════╝${NC}"
echo ""

log_step 1 "Checking Python"
if ! command -v python3 &>/dev/null; then
    log_error "Python 3 required"
    exit 1
fi
PYVER=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
log_info "Python $PYVER"

log_step 2 "Checking network"
if ! ping -c 1 -W 2 pypi.org &>/dev/null 2>&1; then
    log_error "No internet"
    exit 1
fi
log_info "Network OK"

log_step 3 "Checking disk"
FREE_MB=$(df -m . 2>/dev/null | tail -1 | awk '{print $4}' || echo "999")
if [ "$FREE_MB" -lt "$MIN_DISK_MB" ]; then
    log_error "Disk space: ${FREE_MB}MB (need ${MIN_DISK_MB}MB)"
    exit 1
fi
log_info "Disk: ${FREE_MB}MB free"

log_step 4 "Detecting platform"
if [ -n "${PREFIX:-}" ]; then
    log_info "Platform: Termux/Android"
elif grep -qi microsoft /proc/version 2>/dev/null; then
    log_info "Platform: WSL"
elif [ "$(uname)" = "Darwin" ]; then
    log_info "Platform: macOS"
else
    log_info "Platform: Linux"
fi

log_step 5 "Creating structure"
mkdir -p data backups logs config
log_info "Directories created"

log_step 6 "Installing core"
$PYTHON_CMD -m pip install --upgrade pip --quiet 2>/dev/null || log_warn "pip upgrade skipped"
if ! $PYTHON_CMD -m pip install -r requirements-core.txt --quiet; then
    log_error "Core install failed"
    exit 1
fi
log_info "Core installed"

echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║      Installation Complete!                    ║${NC}"
echo -e "${GREEN}${BOLD}╠══════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}${BOLD}║  FlowCore v1.0.1 Core                          ║${NC}"
echo -e "${GREEN}${BOLD}║  Python: $PYVER                                 ║${NC}"
echo -e "${GREEN}${BOLD}║  Status: CLI Ready                             ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo "Test:     python3 flowcore.py version"
echo "Selftest: python3 flowcore.py selftest"
echo "API:      bash install_api.sh"
echo ""
