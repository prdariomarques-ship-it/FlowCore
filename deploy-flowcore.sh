#!/bin/bash

################################################################################
# FlowCore Web Frontend Deployment Script
# Safe frontend update without affecting backend, database, or configuration
################################################################################

set -e

# Configuration
FLOWCORE_WEB_PATH="${FLOWCORE_WEB_PATH:-/home/user/flowcore/web}"
BACKUP_DIR="${BACKUP_DIR:-/home/user/flowcore/backups}"
INDEX_FILE="index.html"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
log_info() {
  echo -e "${GREEN}✅${NC} $1"
}

log_warn() {
  echo -e "${YELLOW}⚠️${NC}  $1"
}

log_error() {
  echo -e "${RED}❌${NC} $1"
}

check_path() {
  if [ ! -d "$FLOWCORE_WEB_PATH" ]; then
    log_error "Frontend path not found: $FLOWCORE_WEB_PATH"
    log_warn "Set FLOWCORE_WEB_PATH environment variable if different"
    exit 1
  fi
  log_info "Frontend path confirmed: $FLOWCORE_WEB_PATH"
}

create_backup() {
  mkdir -p "$BACKUP_DIR"
  local backup_file="$BACKUP_DIR/${INDEX_FILE}.${TIMESTAMP}.bak"
  cp "$FLOWCORE_WEB_PATH/$INDEX_FILE" "$backup_file"
  log_info "Backup created: $backup_file"
  echo "$backup_file"
}

validate_file() {
  local file="$1"
  if [ ! -f "$file" ]; then
    log_error "File not found: $file"
    exit 1
  fi

  # Check if it's valid HTML
  if ! grep -q "<!DOCTYPE html>" "$file" 2>/dev/null; then
    log_error "File does not appear to be valid HTML"
    exit 1
  fi

  # Check for critical elements
  if ! grep -q "FlowCore" "$file" 2>/dev/null; then
    log_error "HTML missing 'FlowCore' identifier"
    exit 1
  fi

  log_info "File validation passed"
}

deploy_file() {
  local source_file="$1"
  local dest_file="$FLOWCORE_WEB_PATH/$INDEX_FILE"

  # Get current permissions
  local perms=$(stat -c %a "$dest_file" 2>/dev/null || stat -f %A "$dest_file" 2>/dev/null)

  # Copy file
  cp "$source_file" "$dest_file"

  # Restore permissions
  if [ -n "$perms" ]; then
    chmod "$perms" "$dest_file"
  fi

  log_info "File deployed: $dest_file"
}

verify_deployment() {
  local deployed_file="$FLOWCORE_WEB_PATH/$INDEX_FILE"

  # Verify file exists and has content
  if [ ! -s "$deployed_file" ]; then
    log_error "Deployed file is empty or missing"
    exit 1
  fi

  # Verify key elements
  if ! grep -q "FlowCore" "$deployed_file"; then
    log_error "Verification failed: key elements missing"
    exit 1
  fi

  log_info "Deployment verification passed"
}

restart_service() {
  log_info "Checking if restart needed..."

  # Check if FlowCore is running
  if pgrep -f "flowcore" > /dev/null 2>&1; then
    log_warn "FlowCore is running. Consider restarting:"
    log_warn "  bash deploy/restart.sh"
  else
    log_info "FlowCore not running (no restart needed)"
  fi
}

show_usage() {
  cat << EOF
Usage: $0 <index.html>

Deploy a new index.html to FlowCore frontend safely.

Arguments:
  index.html    Path to the new index.html file

Environment Variables:
  FLOWCORE_WEB_PATH    Path to FlowCore web directory
                      (default: /home/user/flowcore/web)
  BACKUP_DIR          Directory for backups
                      (default: /home/user/flowcore/backups)

Example:
  $0 web/index.html
  FLOWCORE_WEB_PATH=/opt/flowcore/web $0 index.html

Safety Features:
  - Creates timestamped backup before deployment
  - Validates HTML structure
  - Preserves file permissions
  - Doesn't modify backend/database/config
  - Verifies successful deployment

Rollback:
  Use rollback-flowcore.sh to restore previous version
EOF
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

SOURCE_FILE="$1"

echo "╔════════════════════════════════════════════════════════════╗"
echo "║        FlowCore Frontend Deployment - Safe Mode            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Execute deployment
check_path
validate_file "$SOURCE_FILE"
BACKUP_FILE=$(create_backup)
deploy_file "$SOURCE_FILE"
verify_deployment
restart_service

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                 ✅ DEPLOYMENT SUCCESSFUL                   ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Deployed to:  $FLOWCORE_WEB_PATH/index.html"
echo "Backup at:    $BACKUP_FILE"
echo ""
echo "Next steps:"
echo "  1. Open browser: http://localhost:8080 (or your URL)"
echo "  2. Clear cache (Ctrl+Shift+Del)"
echo "  3. Verify changes display correctly"
echo ""
echo "If something went wrong:"
echo "  bash rollback-flowcore.sh $BACKUP_FILE"
echo ""
