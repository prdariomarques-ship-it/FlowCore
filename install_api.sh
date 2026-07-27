#!/usr/bin/env bash
set -euo pipefail

PYTHON_CMD="python3"
TUR_INDEX="https://termux-user-repository.github.io/pypi/"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

echo -e "${GREEN}Installing FlowCore API...${NC}"

if [ -n "${PREFIX:-}" ]; then
    log_info "Termux detected: trying TUR first..."
    if $PYTHON_CMD -m pip install pydantic-core --extra-index-url "$TUR_INDEX" --quiet 2>&1; then
        log_info "pydantic-core OK"
    else
        log_error "pydantic-core failed on Termux"
        log_error "Option 1: Install on desktop/laptop instead"
        log_error "Option 2: Use pydantic v1: pip install 'pydantic==1.10.12'"
        exit 1
    fi
fi

if ! $PYTHON_CMD -m pip install -r requirements-api.txt --quiet 2>&1; then
    log_error "API installation failed"
    exit 1
fi

echo -e "${GREEN}✓ API installed. Run: python3 flowcore.py serve${NC}"
