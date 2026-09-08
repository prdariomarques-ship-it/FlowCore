#!/bin/bash

################################################################################
# FlowCore Rollback Script
# Restore previous version of index.html from backup
################################################################################

set -e

# Configuration
FLOWCORE_WEB_PATH="${FLOWCORE_WEB_PATH:-/home/user/flowcore/web}"
BACKUP_DIR="${BACKUP_DIR:-/home/user/flowcore/backups}"
INDEX_FILE="index.html"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}✅${NC} $1"; }
log_warn() { echo -e "${YELLOW}⚠️${NC}  $1"; }
log_error() { echo -e "${RED}❌${NC} $1"; }

show_usage() {
  cat << EOF
Usage: $0 [backup_file | --latest]

Restore index.html from a backup file.

Arguments:
  backup_file         Path to backup file (e.g., backups/index.html.20260905_183045.bak)
  --latest           Restore the most recent backup automatically

Environment Variables:
  FLOWCORE_WEB_PATH   Path to FlowCore web directory
  BACKUP_DIR          Directory containing backups

Examples:
  $0 /home/user/flowcore/backups/index.html.20260905_183045.bak
  $0 --latest
  FLOWCORE_WEB_PATH=/opt/flowcore/web $0 --latest
EOF
}

list_backups() {
  if [ ! -d "$BACKUP_DIR" ] || [ -z "$(ls -1 "$BACKUP_DIR"/*.bak 2>/dev/null)" ]; then
    log_error "No backups found in $BACKUP_DIR"
    exit 1
  fi

  echo "Available backups:"
  ls -lhS "$BACKUP_DIR"/*.bak 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
}

get_latest_backup() {
  if [ ! -d "$BACKUP_DIR" ]; then
    log_error "Backup directory not found: $BACKUP_DIR"
    exit 1
  fi

  local latest=$(ls -t "$BACKUP_DIR"/*.bak 2>/dev/null | head -1)
  if [ -z "$latest" ]; then
    log_error "No backups found"
    list_backups
    exit 1
  fi
  echo "$latest"
}

verify_backup() {
  local backup_file="$1"

  if [ ! -f "$backup_file" ]; then
    log_error "Backup file not found: $backup_file"
    list_backups
    exit 1
  fi

  if ! grep -q "<!DOCTYPE html>" "$backup_file" 2>/dev/null; then
    log_error "Backup file does not appear to be valid HTML"
    exit 1
  fi

  log_info "Backup verified: $backup_file"
}

restore_backup() {
  local backup_file="$1"
  local dest_file="$FLOWCORE_WEB_PATH/$INDEX_FILE"
  local restore_backup="$BACKUP_DIR/${INDEX_FILE}.restore.${$(date +%s)}.bak"

  # Create backup of current (broken) version
  mkdir -p "$BACKUP_DIR"
  if [ -f "$dest_file" ]; then
    cp "$dest_file" "$restore_backup"
    log_info "Current version backed up to: $restore_backup"
  fi

  # Get permissions from backup
  local perms=$(stat -c %a "$backup_file" 2>/dev/null || stat -f %A "$backup_file" 2>/dev/null)

  # Restore backup
  cp "$backup_file" "$dest_file"

  # Restore permissions
  if [ -n "$perms" ]; then
    chmod "$perms" "$dest_file"
  fi

  log_info "Restored: $dest_file"
}

verify_restoration() {
  local dest_file="$FLOWCORE_WEB_PATH/$INDEX_FILE"

  if [ ! -s "$dest_file" ]; then
    log_error "Restored file is empty or missing"
    exit 1
  fi

  if ! grep -q "FlowCore" "$dest_file"; then
    log_error "Verification failed: restored file appears corrupted"
    exit 1
  fi

  log_info "Restoration verified successfully"
}

################################################################################
# Main
################################################################################

if [ $# -eq 0 ]; then
  show_usage
  exit 1
fi

if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
  show_usage
  exit 0
fi

echo "╔════════════════════════════════════════════════════════════╗"
echo "║         FlowCore Frontend Rollback - Recovery Mode         ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Determine backup file
if [ "$1" = "--latest" ]; then
  BACKUP_FILE=$(get_latest_backup)
  log_info "Using latest backup: $BACKUP_FILE"
else
  BACKUP_FILE="$1"
fi

# Execute rollback
verify_backup "$BACKUP_FILE"
restore_backup "$BACKUP_FILE"
verify_restoration

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                  ✅ ROLLBACK SUCCESSFUL                    ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Restored to: $FLOWCORE_WEB_PATH/index.html"
echo "From backup: $BACKUP_FILE"
echo ""
echo "Next steps:"
echo "  1. Clear browser cache (Ctrl+Shift+Del)"
echo "  2. Reload page to verify"
echo "  3. If still broken, try another backup:"
echo ""
list_backups
echo ""
echo "After confirming rollback worked:"
echo "  rm $BACKUP_FILE"
echo ""
