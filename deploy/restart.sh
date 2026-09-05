#!/data/data/com.termux/files/usr/bin/bash
# FlowCore — restart seguro para Termux: atualiza o código (git pull), mata
# os processos antigos e sobe FlowCore + cloudflared de novo, num comando só.
#
# Por que isto existe: depois de um `git pull`, o código novo só entra em
# vigor quando o processo Python é reiniciado. Nesse aparelho, `pkill`/`pgrep`
# podem falhar com "Bad system call" (kernel Android bloqueando a syscall),
# "Forçar parada" no app do Termux nem sempre mata processos em segundo
# plano, e reabrir o Termux NÃO dispara o script de boot de novo — isso só
# acontece quando o telefone reinicia de verdade. Este script substitui toda
# essa dança manual: encontra e mata os processos antigos lendo /proc
# diretamente (ver deploy/proc_utils.sh), depois sobe tudo de novo.
#
# Uso (dentro de ~/FlowCore):
#   bash deploy/restart.sh            # git pull + restart (padrão)
#   bash deploy/restart.sh --no-pull  # só restart, sem mexer no git
set -u

BASE="$HOME/FlowCore"
LOGDIR="$HOME/.config/flowcore"
PIDDIR="$HOME/.flowcore/run"
mkdir -p "$LOGDIR" "$PIDDIR"

cd "$BASE" || { echo "ERRO: $BASE não encontrado"; exit 1; }
. "$BASE/deploy/proc_utils.sh"

_log() { echo "$(date -Is) $*" | tee -a "$LOGDIR/restart.log"; }

_log "=== Restart iniciado ==="

if [ "${1:-}" != "--no-pull" ]; then
    _log "git pull origin main..."
    git pull origin main 2>&1 | tee -a "$LOGDIR/restart.log"
fi

_log "Encerrando processos antigos (se houver)..."
_proc_kill "flowcore.py serve"
_proc_kill "cloudflared tunnel run"

export FLOWCORE__API__HOST="${FLOWCORE_BIND_HOST:-0.0.0.0}"

_log "Iniciando FlowCore..."
nohup python3 flowcore.py serve >> "$LOGDIR/flowcore.log" 2>&1 &
echo $! > "$PIDDIR/flowcore.pid"

TOKEN_FILE="$HOME/.config/cloudflared/tunnel-token"
if [ -r "$TOKEN_FILE" ]; then
    set -a; . "$TOKEN_FILE"; set +a
    if [ -n "${TUNNEL_TOKEN:-}" ]; then
        _log "Iniciando cloudflared..."
        nohup cloudflared tunnel run --token "$TUNNEL_TOKEN" >> "$LOGDIR/cloudflared.log" 2>&1 &
        echo $! > "$PIDDIR/cloudflared.pid"
    else
        _log "AVISO: TUNNEL_TOKEN vazio — cloudflared não iniciado"
    fi
else
    _log "AVISO: $TOKEN_FILE ausente — cloudflared não iniciado"
fi

_log "Aguardando FlowCore responder em 127.0.0.1:8080..."
tries=0
until curl -fsS --max-time 3 http://127.0.0.1:8080/api/health >/dev/null 2>&1; do
    tries=$((tries + 1))
    if [ "$tries" -ge 30 ]; then
        _log "ERRO: FlowCore não respondeu após 60s — confira $LOGDIR/flowcore.log"
        exit 1
    fi
    sleep 2
done

_log "FlowCore no ar (pid=$(cat "$PIDDIR/flowcore.pid" 2>/dev/null))"
echo
curl -fsS --max-time 3 http://127.0.0.1:8080/api/health
echo
