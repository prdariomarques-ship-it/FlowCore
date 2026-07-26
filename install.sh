#!/usr/bin/env bash
# ============================================================================
# FlowCore — One-line installer for Termux / Android
# ============================================================================
# Usage:
#   git clone https://github.com/prdariomarques-ship-it/FlowCore.git
#   cd FlowCore
#   bash install.sh
#
# This script:
#   1. Detects the platform (Termux vs standard Linux)
#   2. Installs Python dependencies
#   3. Creates required directories
#   4. Validates the installation
#   5. Does NOT start any server automatically
# ============================================================================
set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ── Platform detection ────────────────────────────────────────────────────
IS_TERMUX=false
PYTHON_CMD="python3"

if [ -n "${PREFIX:-}" ] && [ -f "${PREFIX}/../usr/bin/apt" ] 2>/dev/null; then
    IS_TERMUX=true
    info "Detected Termux environment"
elif [ -n "${PREFIX:-}" ]; then
    IS_TERMUX=true
    info "Detected Termux-like environment"
fi

# ── Pre-flight checks ─────────────────────────────────────────────────────
info "Checking Python..."
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    error "Python 3 is required but not found."
    if [ "$IS_TERMUX" = true ]; then
        info "Run: pkg install python"
    else
        info "Install Python 3.11+ from your package manager."
    fi
    exit 1
fi

# Use python3 if available, else python
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
else
    PYTHON_CMD="python"
fi

PYTHON_VERSION=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
info "Python version: $PYTHON_VERSION"

# ── Termux-specific setup ─────────────────────────────────────────────────
if [ "$IS_TERMUX" = true ]; then
    info "Updating Termux packages..."
    pkg update -y 2>/dev/null || apt update -y 2>/dev/null || true
    info "Installing required Termux packages..."
    pkg install -y python openssl 2>/dev/null || apt install -y python3 openssl 2>/dev/null || true
fi

# ── Create directories ────────────────────────────────────────────────────
info "Creating directories..."
mkdir -p data logs backups

# ── Install Python dependencies ────────────────────────────────────────────
info "Installing Python dependencies..."
$PYTHON_CMD -m pip install --upgrade pip 2>/dev/null || true
$PYTHON_CMD -m pip install --user -r requirements.txt

# ── Copy default config ───────────────────────────────────────────────────
if [ ! -f config/local.yml ]; then
    info "No local config found — using defaults from config/default.yml"
fi

# ── Validate ──────────────────────────────────────────────────────────────
info "Validating installation..."
VALIDATION_OK=true

if ! $PYTHON_CMD -c "import yaml" 2>/dev/null; then
    error "yaml module not available"
    VALIDATION_OK=false
fi

if ! $PYTHON_CMD -c "import fastapi" 2>/dev/null; then
    error "fastapi module not available"
    VALIDATION_OK=false
fi

if ! $PYTHON_CMD -c "import loguru" 2>/dev/null; then
    error "loguru module not available"
    VALIDATION_OK=false
fi

# ── Security check ────────────────────────────────────────────────────────
info "Running security checks..."
if grep -q "0.0.0.0" config/default.yml 2>/dev/null; then
    warn "API host is set to 0.0.0.0 — this is INSECURE. Change to 127.0.0.1"
else
    info "API is bound to localhost only — OK"
fi

# ── Final report ──────────────────────────────────────────────────────────
echo ""
echo "=============================================="
echo "  FlowCore Installation Complete"
echo "=============================================="
echo "  Python:     $PYTHON_VERSION"
echo "  Termux:     $IS_TERMUX"
echo "  Location:   $(pwd)"
echo "=============================================="
echo ""
info "Next steps:"
echo "  Start the API:   python3 flowcore.py serve"
echo "  Run daemon:      python3 daemon.py"
echo "  Validate:        bash validate_android.sh"
echo "  Health check:    bash doctor.sh"
echo ""

if [ "$VALIDATION_OK" = false ]; then
    error "Some checks failed. Run 'bash doctor.sh' for details."
    exit 1
fi

info "All checks passed!"
