#!/bin/bash
set -e
REPO="$HOME/FlowCore"
SYSTEMD_DIR="$HOME/.config/systemd/user"
CF_TOKEN_FILE="$HOME/.config/cloudflared/tunnel-token"

echo "=== FlowCore Persistence Install ==="
echo "User: $(whoami) | Home: $HOME"

# 1. Linger (necessário para serviços user sem login)
sudo loginctl enable-linger "$(whoami)" 2>/dev/null && echo "linger: enabled" || echo "linger: ja ok"

# 2. Matar processos nohup antigos
kill "$(pgrep -f 'nohup.*flowcore.py' 2>/dev/null)" 2>/dev/null || true
kill "$(pgrep -f 'cloudflared tunnel' 2>/dev/null)" 2>/dev/null || true
sleep 2

# 3. Criar diretórios
mkdir -p "$SYSTEMD_DIR"
mkdir -p "$(dirname "$CF_TOKEN_FILE")"

# 4. Verificar token do tunnel nomeado
if [ ! -f "$CF_TOKEN_FILE" ]; then
  echo ""
  echo "⚠️  TOKEN DO TUNNEL NÃO ENCONTRADO"
  echo "Crie o arquivo antes de continuar:"
  echo "  mkdir -p ~/.config/cloudflared"
  echo "  echo 'TUNNEL_TOKEN=eyJhIjo...' > ~/.config/cloudflared/tunnel-token"
  echo "  chmod 600 ~/.config/cloudflared/tunnel-token"
  echo ""
  echo "Obtenha o token em: Zero Trust → Networks → Tunnels → (flowcore) → Configure"
  echo ""
  read -r -p "Continuar sem tunnel nomeado (usa URL efêmera)? [s/N] " RESP
  if [[ "$RESP" != "s" && "$RESP" != "S" ]]; then
    echo "Abortado. Configure o token e rode novamente."
    exit 1
  fi
  # Fallback: ephemeral tunnel
  sed "s|%u|$(whoami)|g" "$REPO/deploy/cloudflared.service" \
    | sed 's|EnvironmentFile=.*||' \
    | sed 's|ExecStart=.* tunnel run --token .*|ExecStart=/usr/local/bin/cloudflared tunnel --url http://127.0.0.1:8090|' \
    > "$SYSTEMD_DIR/cloudflared.service"
  TUNNEL_MODE="efêmero (trycloudflare.com)"
else
  # Named tunnel
  chmod 600 "$CF_TOKEN_FILE"
  sed "s|%u|$(whoami)|g" "$REPO/deploy/cloudflared.service" > "$SYSTEMD_DIR/cloudflared.service"
  TUNNEL_MODE="nomeado (URL permanente)"
fi

# 5. Instalar flowcore.service
sed "s|%u|$(whoami)|g" "$REPO/deploy/flowcore.service" > "$SYSTEMD_DIR/flowcore.service"

# 6. Descobrir cloudflared real
CF_BIN=$(which cloudflared 2>/dev/null || ls "$HOME/.local/bin/cloudflared" 2>/dev/null || echo "/usr/local/bin/cloudflared")
if [ "$CF_BIN" != "/usr/local/bin/cloudflared" ]; then
  sed -i "s|/usr/local/bin/cloudflared|$CF_BIN|g" "$SYSTEMD_DIR/cloudflared.service"
  echo "cloudflared em: $CF_BIN"
fi

# 7. Descobrir python real
PY_BIN=$(conda run which python3 2>/dev/null || which python3)
if [ -n "$PY_BIN" ] && [ "$PY_BIN" != "/home/$(whoami)/miniconda3/bin/python3" ]; then
  sed -i "s|/home/$(whoami)/miniconda3/bin/python3|$PY_BIN|g" "$SYSTEMD_DIR/flowcore.service"
  echo "python em: $PY_BIN"
fi

# 8. Reload + enable + start
systemctl --user daemon-reload
systemctl --user enable flowcore cloudflared
systemctl --user start flowcore
sleep 10
systemctl --user start cloudflared
sleep 15

# 9. Status
echo ""
echo "=== Status (tunnel: $TUNNEL_MODE) ==="
systemctl --user is-active flowcore && echo "flowcore: ACTIVE" || echo "flowcore: FALHOU"
systemctl --user is-active cloudflared && echo "cloudflared: ACTIVE" || echo "cloudflared: FALHOU"
curl -s --max-time 10 http://127.0.0.1:8090/api/health || echo "(health check falhou)"
echo ""

# 10. URL do tunnel
if [ "$TUNNEL_MODE" = "efêmero (trycloudflare.com)" ]; then
  URL=$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "$HOME/tunnel.log" 2>/dev/null | tail -1)
  echo "TUNNEL_URL=$URL (efêmero, muda a cada reinicialização)"
else
  echo "Tunnel nomeado ativo. Configure o hostname público em:"
  echo "  Zero Trust → Networks → Tunnels → flowcore → Public Hostname"
  echo "  Subdomain: flowcore | Domain: <seu-workers.dev> | Service: http://127.0.0.1:8090"
  echo ""
  URL=$(grep -Eo 'https://[a-z0-9.-]+' "$HOME/tunnel.log" 2>/dev/null | grep -v trycloudflare | tail -1)
  [ -n "$URL" ] && echo "TUNNEL_URL=$URL" || echo "TUNNEL_URL: ver tunnel.log após configurar hostname"
fi
[ -n "$URL" ] && curl -s --max-time 20 "$URL/api/health" || true
