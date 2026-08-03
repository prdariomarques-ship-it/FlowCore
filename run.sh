#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# Ensure directories exist
mkdir -p data logs backups

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] Python 3 not found. Run ./install.sh first."
    exit 1
fi

echo ""
echo "Starting FlowCore..."
echo ""

python3 flowcore.py run
