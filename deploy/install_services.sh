#!/bin/bash
set -e
REPO="$HOME/FlowCore"
SYSTEMD_DIR="$HOME/.config/systemd/user"

echo "=== FlowCore Persistence Install ==="
echo "User: $(whoami) | Home: $HOME"

# 1. Linger (necessário para serviços user sem login)
sudo loginctl enable-linger "$(whoami)" 2>/dev/null && echo "linger: enabled" || echo "linger: ja ok"

# 2. Matar processos nohup antigos
kill "$(pgrep -f 'nohup.*flowcore.py' 2>/dev/null)" 2>/dev/null || true
kill "$(pgrep -f 'cloudflared tunnel' 2>/dev/null)" 2>/dev/null || true
sleep 2

# 3. Criar diretório systemd user
mkdir -p "$SYSTEMD_DIR"

# 4. Instalar arquivos de serviço (substituir %u pelo usuário real)
sed "s|%u|$(whoami)|g" "$REPO/deploy/flowcore.service" > "$SYSTEMD_DIR/flowcore.service"
sed "s|%u|$(whoami)|g" "$REPO/deploy/cloudflared.service" > "$SYSTEMD_DIR/cloudflared.service"

# 5. Descobrir cloudflared real
CF_BIN=$(which cloudflared 2>/dev/null || ls "$HOME/.local/bin/cloudflared" 2>/dev/null || ls /usr/local/bin/cloudflared 2>/dev/null || echo "")
if [ -n "$CF_BIN" ] && [ "$CF_BIN" != "/usr/local/bin/cloudflared" ]; then
  sed -i "s|/usr/local/bin/cloudflared|$CF_BIN|g" "$SYSTEMD_DIR/cloudflared.service"
  echo "cloudflared em: $CF_BIN"
fi

# 6. Descobrir python real
PY_BIN=$(conda run which python3 2>/dev/null || which python3)
if [ -n "$PY_BIN" ] && [ "$PY_BIN" != "/home/$(whoami)/miniconda3/bin/python3" ]; then
  sed -i "s|/home/$(whoami)/miniconda3/bin/python3|$PY_BIN|g" "$SYSTEMD_DIR/flowcore.service"
  echo "python em: $PY_BIN"
fi

# 7. Instalar watchdog
cp "$REPO/scripts/flowcore_watchdog.sh" "$HOME/flowcore_watchdog.sh"
chmod +x "$HOME/flowcore_watchdog.sh"
(crontab -l 2>/dev/null | grep -v flowcore_watchdog; echo "*/5 * * * * $HOME/flowcore_watchdog.sh") | crontab -

# 8. Reload + enable + start
systemctl --user daemon-reload
systemctl --user enable flowcore cloudflared
systemctl --user start flowcore
sleep 10
systemctl --user start cloudflared
sleep 15

# 9. Status
echo ""
echo "=== Status ==="
systemctl --user is-active flowcore && echo "flowcore: ACTIVE" || echo "flowcore: FALHOU"
systemctl --user is-active cloudflared && echo "cloudflared: ACTIVE" || echo "cloudflared: FALHOU"
curl -s --max-time 10 http://127.0.0.1:8090/api/health
echo ""

# 10. URL do túnel
URL=$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "$HOME/tunnel.log" 2>/dev/null | tail -1)
echo "TUNNEL_URL=$URL"
[ -n "$URL" ] && curl -s --max-time 20 "$URL/api/health" || echo "aguardar tunnel.log..."
