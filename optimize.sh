#!/usr/bin/env bash
# ============================================================================
# FlowCore — Performance Optimizer
# ============================================================================
# Optimizes the installation for Termux / Android:
#   1. Trims log files
#   2. Compiles Python bytecode
#   3. Cleans __pycache__
#   4. Reports disk savings
# ============================================================================
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${GREEN}[OPTIMIZE]${NC} $*"; }

echo "=============================================="
echo "  FlowCore Optimizer"
echo "=============================================="
echo ""

# ── 1. Trim logs ─────────────────────────────────────────────────────────
BEFORE=$(du -sh logs/ 2>/dev/null | cut -f1 || echo "0B")
info "Log directory before: $BEFORE"

if [ -f "logs/flowcore.log" ]; then
    # Keep only last 500 lines
    tail -500 logs/flowcore.log > logs/flowcore.tmp
    mv logs/flowcore.tmp logs/flowcore.log
fi

AFTER=$(du -sh logs/ 2>/dev/null | cut -f1 || echo "0B")
info "Log directory after: $AFTER"

# ── 2. Clean __pycache__ ─────────────────────────────────────────────────
info "Cleaning __pycache__ directories..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true

# ── 3. Re-compile optimized bytecode ─────────────────────────────────────
info "Compiling optimized bytecode (.pyo)..."
python3 -O -m compileall -q . 2>/dev/null || true

# ── 4. Summary ───────────────────────────────────────────────────────────
echo ""
echo "=============================================="
echo "  Optimization complete"
echo "  Project size: $(du -sh . 2>/dev/null | cut -f1)"
echo "=============================================="
