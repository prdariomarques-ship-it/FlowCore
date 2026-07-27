#!/usr/bin/env bash
# ============================================================================
# FlowCore — Professional Installer v1.0.0
# ============================================================================
# Usage:
#   bash install.sh
#
# Features:
#   - Internet connectivity check
#   - Disk space validation (minimum 100 MB free)
#   - Rollback on failure
#   - Detailed error handling and logging
#   - Friendly messages for all platforms
#   - Platform auto-detection (Termux / Linux / macOS)
# ============================================================================
set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────
MIN_DISK_MB=100
INSTALL_LOG="logs/install.log"
ROLLBACK_MARKER=".install_rollback"
PYTHON_CMD="python3"

# ── Colours ───────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ── Logging ───────────────────────────────────────────────────────────────
mkdir -p logs
exec > >(tee -a "$INSTALL_LOG") 2>&1

log_info()  { echo -e "${GREEN}[INFO]${NC}    $(date '+%H:%M:%S') $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}    $(date '+%H:%M:%S') $*"; }
log_error() { echo -e "${RED}[ERROR]${NC}   $(date '+%H:%M:%S') $*"; }
log_step()  { echo -e "\n${CYAN}${BOLD}[STEP $1/7]${NC} $2"; }

# ── Banner ────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║         FlowCore Installer v1.0.0                ║${NC}"
echo -e "${BOLD}${CYAN}║   Workflow Automation Engine for Android/Termux  ║${NC}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# ── Rollback function ────────────────────────────────────────────────────
rollback() {
    echo ""
    echo -e "${RED}${BOLD}══════════════════════════════════════════════════${NC}"
    echo -e "${RED}[ROLLBACK]${NC} Installation failed. Reverting changes..."
    echo -e "${RED}${BOLD}══════════════════════════════════════════════════${NC}"

    # Remove directories we created
    for dir in data backups; do
        if [ -d "$dir" ] && [ ! -f "$ROLLBACK_MARKER/$dir" ]; then
            rm -rf "$dir"
            log_info "Removed directory: $dir/"
        fi
    done

    # Uninstall pip packages if we installed them
    if [ -f "$ROLLBACK_MARKER/pip_installed" ]; then
        log_info "Uninstalling Python packages..."
        $PYTHON_CMD -m pip uninstall -y -r requirements.txt 2>/dev/null || true
    fi

    # Clean up rollback marker
    rm -rf "$ROLLBACK_MARKER" 2>/dev/null || true

    echo ""
    log_error "Installation failed. Check logs/install.log for details."
    log_info "Fix the issue and re-run: bash install.sh"
    exit 1
}

trap rollback ERR

# ── STEP 1: Internet Check ───────────────────────────────────────────────
log_step 1 "Checking internet connectivity"

if ping -c 1 -W 3 github.com &>/dev/null; then
    log_info "Internet connection OK"
elif ping -c 1 -W 3 pypi.org &>/dev/null; then
    log_info "Internet connection OK (GitHub blocked, but PyPI reachable)"
elif command -v curl &>/dev/null && curl -s --connect-timeout 3 https://pypi.org/ > /dev/null 2>&1; then
    log_info "Internet connection OK (curl test passed)"
else
    log_error "No internet connection detected"
    log_error "FlowCore requires internet to install Python dependencies."
    log_info "Connect to a network and re-run: bash install.sh"
    exit 1
fi

# ── STEP 2: Disk Space Check ─────────────────────────────────────────────
log_step 2 "Checking available disk space"

FREE_MB=$(df -m . | tail -1 | awk '{print $4}' 2>/dev/null || echo "999")

if [ "$FREE_MB" -lt "$MIN_DISK_MB" ] 2>/dev/null; then
    log_error "Insufficient disk space: ${FREE_MB}MB free (minimum ${MIN_DISK_MB}MB required)"
    log_info "Free up disk space and re-run: bash install.sh"
    exit 1
else
    log_info "Disk space OK: ${FREE_MB}MB free"
fi

# ── STEP 3: Platform Detection ───────────────────────────────────────────
log_step 3 "Detecting platform"

IS_TERMUX=false
IS_MACOS=false

if [ -n "${PREFIX:-}" ]; then
    IS_TERMUX=true
    log_info "Platform: Termux (Android)"
elif [ "$(uname)" = "Darwin" ]; then
    IS_MACOS=true
    log_info "Platform: macOS"
elif [ -f "/etc/os-release" ]; then
    OS_NAME=$(grep '^NAME=' /etc/os-release | cut -d'"' -f2 2>/dev/null || echo "Linux")
    log_info "Platform: $OS_NAME"
else
    log_info "Platform: $(uname) $(uname -m)"
fi

# ── STEP 4: Python Check ─────────────────────────────────────────────────
log_step 4 "Checking Python installation"

if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    log_error "Python 3 is required but not installed"
    if [ "$IS_TERMUX" = true ]; then
        log_info "To install: pkg install python"
    elif [ "$IS_MACOS" = true ]; then
        log_info "To install: brew install python3"
    else
        log_info "To install: sudo apt install python3 python3-pip"
    fi
    exit 1
fi

# Use python3 if available, else python
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
else
    PYTHON_CMD="python"
fi

PYVER=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
log_info "Python version: $PYVER"

if [ "$(echo "$PYVER < 3.11" | bc -l)" = "1" ] 2>/dev/null; then
    log_warn "Python $PYVER is below the minimum recommended (3.11)"
    log_warn "FlowCore may not work correctly. Upgrade to Python 3.11+"
else
    log_info "Python version meets requirements (>= 3.11)"
fi

# ── STEP 5: Install Dependencies ─────────────────────────────────────────
log_step 5 "Installing Python dependencies"

mkdir -p data backups

# Mark rollback points
mkdir -p "$ROLLBACK_MARKER"

# Upgrade pip
log_info "Upgrading pip..."
$PYTHON_CMD -m pip install --upgrade pip --quiet 2>/dev/null || {
    log_warn "Could not upgrade pip (continuing with existing version)"
}

# Install requirements
log_info "Installing dependencies from requirements.txt..."
$PYTHON_CMD -m pip install --user -r requirements.txt --quiet 2>&1 || {
    log_error "Failed to install Python dependencies"
    touch "$ROLLBACK_MARKER/pip_installed"
    rollback
}
touch "$ROLLBACK_MARKER/pip_installed"
log_info "All Python dependencies installed"

# Termux-specific packages
if [ "$IS_TERMUX" = true ]; then
    log_info "Checking Termux system packages..."
    pkg install -y openssl 2>/dev/null || true
fi

# ── STEP 6: Validation ───────────────────────────────────────────────────
log_step 6 "Validating installation"

VALIDATION_ERRORS=0

# Check critical modules
CRITICAL_MODULES="yaml fastapi loguru aiosqlite"
for mod in $CRITICAL_MODULES; do
    if $PYTHON_CMD -c "import $mod" 2>/dev/null; then
        log_info "Module OK: $mod"
    else
        log_error "Module MISSING: $mod"
        ((VALIDATION_ERRORS++)) || true
    fi
done

# Check config
if [ -f "config/default.yml" ]; then
    if $PYTHON_CMD -c "from config.loader import get_config; get_config()" 2>/dev/null; then
        log_info "Configuration: valid"
    else
        log_error "Configuration: failed to load"
        ((VALIDATION_ERRORS++)) || true
    fi
else
    log_error "Configuration: config/default.yml not found"
    ((VALIDATION_ERRORS++)) || true
fi

# Check database directory
if [ -w "data" ]; then
    log_info "Database directory: writable"
else
    log_error "Database directory: not writable"
    ((VALIDATION_ERRORS++)) || true
fi

# Security check
if grep -q "127.0.0.1" config/default.yml 2>/dev/null; then
    log_info "Security: API bound to localhost only"
else
    log_warn "Security: API may be network-exposed. Check config/default.yml"
fi

# ── STEP 7: Final Report ─────────────────────────────────────────────────
log_step 7 "Installation summary"

# Clean up rollback marker on success
rm -rf "$ROLLBACK_MARKER"

echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║         Installation Complete!                  ║${NC}"
echo -e "${GREEN}${BOLD}╠══════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}${BOLD}║  Version:     1.0.0                             ║${NC}"
echo -e "${GREEN}${BOLD}║  Python:      $PYVER                             ║${NC}"
echo -e "${GREEN}${BOLD}║  Platform:    $(if [ "$IS_TERMUX" = true ]; then echo "Termux/Android"; elif [ "$IS_MACOS" = true ]; then echo "macOS"; else echo "Linux"; fi)       ║${NC}"
echo -e "${GREEN}${BOLD}║  Location:    $(pwd)                          ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════╝${NC}"
echo ""

if [ "$VALIDATION_ERRORS" -gt 0 ]; then
    echo -e "${RED}[WARNING]${NC} $VALIDATION_ERRORS validation error(s) detected."
    echo -e "${YELLOW}[INFO]${NC}    Run 'bash repair.sh' to attempt auto-fix."
    echo -e "${YELLOW}[INFO]${NC}    Or run 'bash doctor.sh' for detailed diagnostics."
    exit 1
fi

echo -e "${GREEN}[SUCCESS]${NC} FlowCore is ready to use!"
echo ""
echo -e "${BOLD}Quick Start:${NC}"
echo "  Start API:     python3 flowcore.py serve"
echo "  Start daemon:  python3 daemon.py start"
echo "  Self-test:     python3 flowcore.py selftest"
echo "  Health check:  python3 flowcore.py health"
echo "  Documentation: cat INSTALL_TERMUX.md"
echo ""
echo -e "${BOLD}Log file:${NC} $INSTALL_LOG"
echo ""
