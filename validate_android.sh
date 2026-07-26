#!/usr/bin/env bash
# ============================================================================
# FlowCore — Android / Termux Compatibility Validator
# ============================================================================
# Checks:
#   1. Python version (3.11+)
#   2. Required modules installed
#   3. SQLite available
#   4. Writable directories
#   5. No hardcoded Linux paths
#   6. No root/sudo dependencies
#   7. API binds to localhost
# ============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

pass() { echo -e "  ${GREEN}PASS${NC}  $*"; ((PASS++)); }
fail() { echo -e "  ${RED}FAIL${NC}  $*"; ((FAIL++)); }
warn() { echo -e "  ${YELLOW}WARN${NC}  $*"; ((WARN++)); }

echo "=============================================="
echo "  FlowCore Android Validation"
echo "=============================================="
echo ""

# ── 1. Python version ────────────────────────────────────────────────────
echo "[1/7] Python version check..."
if command -v python3 &>/dev/null; then
    PYVER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    if [ "$(echo "$PYVER >= 3.11" | bc -l)" = "1" ]; then
        pass "Python $PYVER (>= 3.11)"
    else
        fail "Python $PYVER (< 3.11 — minimum required)"
    fi
else
    fail "python3 not found in PATH"
fi

# ── 2. Required modules ──────────────────────────────────────────────────
echo "[2/7] Python module check..."
for mod in fastapi uvicorn loguru pydantic yaml aiosqlite sqlalchemy httpx; do
    if python3 -c "import $mod" 2>/dev/null; then
        pass "Module: $mod"
    else
        fail "Module: $mod (run: pip install -r requirements.txt)"
    fi
done

# ── 3. SQLite ────────────────────────────────────────────────────────────
echo "[3/7] SQLite check..."
if python3 -c "import sqlite3; sqlite3.connect(':memory:')" 2>/dev/null; then
    pass "SQLite available"
else
    fail "SQLite not available"
fi

# ── 4. Writable directories ──────────────────────────────────────────────
echo "[4/7] Directory permissions..."
for dir in logs backups data; do
    if [ -w "$dir" ]; then
        pass "Writable: $dir/"
    else
        fail "Not writable: $dir/"
    fi
done

# ── 5. No hardcoded Linux paths ──────────────────────────────────────────
echo "[5/7] Hardcoded path check..."
if grep -rn "/etc/" --include="*.py" . 2>/dev/null | grep -v "__pycache__" | grep -v ".pyc" | grep -v "install.sh" | head -3; then
    warn "Found references to /etc/ paths (may not exist on Termux)"
else
    pass "No hardcoded Linux system paths"
fi

if grep -rn "sudo" --include="*.py" --include="*.sh" . 2>/dev/null | grep -v "__pycache__" | grep -v "install.sh" | head -3; then
    warn "Found sudo references (not available on Termux)"
else
    pass "No sudo dependencies"
fi

# ── 6. Root/sudo check ───────────────────────────────────────────────────
echo "[6/7] Privilege check..."
if grep -q "auto_root: true" config/default.yml 2>/dev/null; then
    fail "auto_root is enabled (SECURITY RISK)"
else
    pass "auto_root is disabled"
fi

# ── 7. API localhost check ───────────────────────────────────────────────
echo "[7/7] API security check..."
API_HOST=$(python3 -c "
from config.loader import get_config
print(get_config()['api']['host'])
" 2>/dev/null || echo "unknown")

if [ "$API_HOST" = "127.0.0.1" ]; then
    pass "API bound to 127.0.0.1 (localhost only)"
elif [ "$API_HOST" = "0.0.0.0" ]; then
    fail "API bound to 0.0.0.0 (NOT SECURE — accessible from network)"
else
    warn "API host: $API_HOST (verify this is intended)"
fi

# ── Summary ──────────────────────────────────────────────────────────────
echo ""
echo "=============================================="
echo "  Results: $PASS passed, $FAIL failed, $WARN warnings"
echo "=============================================="

if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Some checks failed. Fix before deploying.${NC}"
    exit 1
else
    echo -e "  ${GREEN}All critical checks passed!${NC}"
    exit 0
fi
