#!/usr/bin/env bash
# ============================================================================
# FlowCore — Safe Update Script
# ============================================================================
# Updates the project without losing local configuration or data.
# Usage: bash update.sh
# ============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${GREEN}[UPDATE]${NC} $*"; }
warn() { echo -e "${YELLOW}[UPDATE]${NC} $*"; }

echo "=============================================="
echo "  FlowCore Update"
echo "=============================================="
echo ""

# ── 1. Check for uncommitted changes ─────────────────────────────────────
if [ -d ".git" ]; then
    CHANGES=$(git status --porcelain 2>/dev/null | wc -l)
    if [ "$CHANGES" -gt 0 ]; then
        warn "You have $CHANGES uncommitted changes."
        read -p "  Continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            info "Update cancelled."
            exit 0
        fi
    fi
fi

# ── 2. Backup data ───────────────────────────────────────────────────────
info "Backing up data and config..."
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="backups/update_${TIMESTAMP}"
mkdir -p "$BACKUP_DIR"

if [ -d "data" ]; then
    cp -r data "$BACKUP_DIR/data" 2>/dev/null || true
fi
if [ -f "config/local.yml" ]; then
    cp config/local.yml "$BACKUP_DIR/" 2>/dev/null || true
fi

info "Backup saved to $BACKUP_DIR"

# ── 3. Pull latest ───────────────────────────────────────────────────────
info "Pulling latest changes..."
if git pull origin main 2>/dev/null || git pull origin master 2>/dev/null; then
    info "Updated successfully"
else
    warn "Git pull failed. Trying fetch + rebase..."
    git fetch origin 2>/dev/null || true
    git rebase origin/main 2>/dev/null || git rebase origin/master 2>/dev/null || true
fi

# ── 4. Reinstall dependencies ────────────────────────────────────────────
info "Reinstalling dependencies..."
python3 -m pip install --user -r requirements.txt 2>/dev/null || true

# ── 5. Restore local config ──────────────────────────────────────────────
if [ -f "$BACKUP_DIR/local.yml" ]; then
    cp "$BACKUP_DIR/local.yml" config/local.yml 2>/dev/null || true
    info "Restored local.yml from backup"
fi

# ── Summary ──────────────────────────────────────────────────────────────
echo ""
echo "=============================================="
echo "  Update complete"
echo "  Backup: $BACKUP_DIR"
echo "=============================================="
info "Restart daemon: python3 daemon.py restart"
