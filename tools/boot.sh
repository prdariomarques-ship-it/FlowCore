#!/data/data/com.termux/files/usr/bin/bash
# FlowCore — Termux:Boot startup script
# Install: mkdir -p ~/.termux/boot && cp boot.sh ~/.termux/boot/flowcore.sh && chmod +x ~/.termux/boot/flowcore.sh
#
# This script runs automatically when Android boots (requires Termux:Boot app).
# It starts sshd and the FlowCore daemon + API server.

set -euo pipefail

FLOWCORE_DIR="$HOME/FlowCore"
LOG="$HOME/.flowcore/boot.log"

mkdir -p "$HOME/.flowcore"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Boot script started" >> "$LOG"

# ── 1. Wake lock — keep CPU awake while starting ──────────────────────────────
termux-wake-lock 2>/dev/null || true

# ── 2. Start SSH daemon ───────────────────────────────────────────────────────
if command -v sshd >/dev/null 2>&1; then
    sshd
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] sshd started" >> "$LOG"
fi

# ── 3. Wait for storage to settle after boot ─────────────────────────────────
sleep 5

# ── 4. Start FlowCore daemon ──────────────────────────────────────────────────
if [ -d "$FLOWCORE_DIR" ]; then
    cd "$FLOWCORE_DIR"
    python3 flowcore.py daemon start >> "$LOG" 2>&1 &
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] FlowCore daemon started" >> "$LOG"

    # ── 5. Start API server (web UI on port 8080) ─────────────────────────────
    sleep 2
    nohup python3 flowcore.py serve >> "$HOME/.flowcore/api.log" 2>&1 &
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] FlowCore API server started" >> "$LOG"

    # ── 6. Send boot notification ─────────────────────────────────────────────
    sleep 3
    termux-notification \
        --id 1 \
        --title "FlowCore" \
        --content "✓ FlowCore iniciado — abre http://localhost:8080" \
        2>/dev/null || true
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Boot notification sent" >> "$LOG"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARNING: $FLOWCORE_DIR not found" >> "$LOG"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Boot script complete" >> "$LOG"
