#!/data/data/com.termux/files/usr/bin/bash
# FlowCore — Termux:Boot startup script
# Install: mkdir -p ~/.termux/boot && cp tools/boot.sh ~/.termux/boot/flowcore.sh && chmod +x ~/.termux/boot/flowcore.sh
#
# Starts FlowCore and cloudflared after Android boot (requires Termux:Boot app).
# Both processes are restarted automatically if they crash.

set -u

BASE="$HOME/FlowCore"
LOGDIR="$HOME/.config/flowcore"
mkdir -p "$LOGDIR"
# Mantém Cloudflare compatível e permite acesso privado pelo IP Tailscale do telefone.
# O padrão pode ser sobrescrito por FLOWCORE_BIND_HOST se for necessário restringir a interface.
export FLOWCORE__API__HOST="${FLOWCORE_BIND_HOST:-0.0.0.0}"

command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock

# Wait for the repo to be accessible after boot
while [ ! -d "$BASE" ]; do
    echo "$(date -Is) Repositório não encontrado: $BASE" >> "$LOGDIR/boot.log"
    sleep 10
done

cd "$BASE" || exit 1
. "$BASE/deploy/proc_utils.sh"
echo "$(date -Is) Boot script iniciado; FlowCore em ${FLOWCORE__API__HOST}:8080" >> "$LOGDIR/boot.log"

# Start sshd if available
if command -v sshd >/dev/null 2>&1; then
    sshd
    echo "$(date -Is) sshd iniciado" >> "$LOGDIR/boot.log"
fi

# Keep FlowCore running; restart on crash
while :; do
    if ! _proc_running 'flowcore.py serve'; then
        echo "$(date -Is) Iniciando FlowCore" >> "$LOGDIR/flowcore.log"
        python3 flowcore.py serve >> "$LOGDIR/flowcore.log" 2>&1
        echo "$(date -Is) FlowCore encerrou; reiniciando em 5s" >> "$LOGDIR/flowcore.log"
    fi
    sleep 5
done &

# Aguarda internamente o serviço antes de iniciar auxiliares. O acesso do operador
# deve ser feito pelo domínio Cloudflare ou pelo IP Tailscale, não por localhost.
until curl -fsS --max-time 3 http://127.0.0.1:8080/api/health >/dev/null 2>&1; do
    echo "$(date -Is) Aguardando processo FlowCore" >> "$LOGDIR/boot.log"
    sleep 5
done

echo "$(date -Is) FlowCore pronto — iniciando serviços auxiliares" >> "$LOGDIR/boot.log"

# Start configured Telegram bots. Each executable .sh file is an independent bot.
# Tokens must remain in the bot's private environment/configuration; never put them in this repo.
BOT_DIR="$HOME/.flowcore/bots"
if [ -d "$BOT_DIR" ]; then
    for bot in "$BOT_DIR"/*.sh; do
        [ -x "$bot" ] || continue
        bot_name="$(basename "$bot" .sh)"
        (
            while :; do
                echo "$(date -Is) Iniciando bot $bot_name" >> "$LOGDIR/${bot_name}.log"
                "$bot" >> "$LOGDIR/${bot_name}.log" 2>&1
                echo "$(date -Is) Bot $bot_name encerrou; reiniciando em 10s" >> "$LOGDIR/${bot_name}.log"
                sleep 10
            done
        ) &
    done
fi

termux-notification \
    --id 1 \
    --title "FlowCore" \
    --content "FlowCore iniciado — https://flowcore.admissaoazusa.com.br" \
    2>/dev/null || true

TOKEN_FILE="$HOME/.config/cloudflared/tunnel-token"
if [ ! -r "$TOKEN_FILE" ]; then
    echo "$(date -Is) Token não encontrado: $TOKEN_FILE" >> "$LOGDIR/cloudflared.log"
    exit 1
fi

set -a
. "$TOKEN_FILE"
set +a

if [ -z "${TUNNEL_TOKEN:-}" ]; then
    echo "$(date -Is) TUNNEL_TOKEN vazio" >> "$LOGDIR/cloudflared.log"
    exit 1
fi

# Keep cloudflared running; restart on crash
while :; do
    echo "$(date -Is) Iniciando cloudflared" >> "$LOGDIR/cloudflared.log"
    cloudflared tunnel run --token "$TUNNEL_TOKEN" >> "$LOGDIR/cloudflared.log" 2>&1
    echo "$(date -Is) cloudflared encerrou; reiniciando em 10s" >> "$LOGDIR/cloudflared.log"
    sleep 10
done
