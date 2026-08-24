#!/data/data/com.termux/files/usr/bin/bash
# FlowCore + cloudflared watchdog para Termux
# Uso:  bash ~/FlowCore/deploy/termux_watchdog.sh &
# Ou copie para ~/.termux/boot/ para execução automática no boot (via Termux:Boot).
#
# O watchdog verifica a cada 60s se FlowCore e cloudflared estão vivos.
# Se um processo morrer, reinicia e registra no log.

FLOWCORE_DIR="$HOME/FlowCore"
LOG="$HOME/.flowcore/tunnel_watchdog.log"
CF_TOKEN_FILE="$HOME/.config/cloudflared/tunnel-token"
FLOWCORE_PORT=8080
CHECK_INTERVAL=60

mkdir -p "$HOME/.flowcore"

_log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

_flowcore_running() {
    pgrep -f "flowcore.py serve" >/dev/null 2>&1
}

_cloudflared_running() {
    pgrep -f "cloudflared tunnel run" >/dev/null 2>&1
}

_start_flowcore() {
    _log "Iniciando FlowCore..."
    cd "$FLOWCORE_DIR" || return
    nohup python3 flowcore.py serve >> "$HOME/.flowcore/api.log" 2>&1 &
    sleep 3
    if _flowcore_running; then
        _log "FlowCore OK (pid=$!)"
    else
        _log "ERRO: FlowCore não iniciou"
    fi
}

_start_cloudflared() {
    [ -f "$CF_TOKEN_FILE" ] || { _log "INFO: $CF_TOKEN_FILE ausente — tunnel ignorado"; return; }
    set -a; source "$CF_TOKEN_FILE"; set +a
    [ -n "${TUNNEL_TOKEN:-}" ] || { _log "ERRO: TUNNEL_TOKEN vazio"; return; }
    _log "Iniciando cloudflared..."
    nohup cloudflared tunnel run --token "$TUNNEL_TOKEN" >> "$LOG" 2>&1 &
    sleep 5
    if _cloudflared_running; then
        _log "cloudflared OK (pid=$!)"
    else
        _log "ERRO: cloudflared não iniciou"
    fi
}

_log "=== Watchdog iniciado (PID=$$) ==="

while true; do
    if ! _flowcore_running; then
        _log "FlowCore parou — reiniciando"
        _start_flowcore
    fi

    if ! _cloudflared_running; then
        _log "cloudflared parou — reiniciando"
        _start_cloudflared
    fi

    sleep "$CHECK_INTERVAL"
done
