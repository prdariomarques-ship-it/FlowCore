#!/data/data/com.termux/files/usr/bin/bash
# Atualiza a camada de mercado e comprova a API local do FlowCore no Termux.
# Não grava tokens nem modifica a configuração privada do Cloudflare/Telegram.

set -eu

BASE="$HOME/FlowCore"
BRANCH="claude/flowcore-architecture-consolidation-h95fi2"
BOOT="$HOME/.termux/boot/flowcore.sh"
LOGDIR="$HOME/.config/flowcore"
PUBLIC_URL="https://flowcore.admissaoazusa.com.br"

if [ ! -d "$BASE/.git" ]; then
  echo "ERRO: repositório FlowCore não encontrado em $BASE" >&2
  exit 1
fi

cd "$BASE"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

# yfinance requer lxml. No Termux ARM64 o lxml é compilado localmente, então
# as bibliotecas e cabeçalhos do sistema precisam existir antes do pip.
if command -v pkg >/dev/null 2>&1; then
  pkg install -y libxml2 libxslt clang pkg-config
fi

export CFLAGS="${CFLAGS:-} -I${PREFIX:-/data/data/com.termux/files/usr}/include"
export LDFLAGS="${LDFLAGS:-} -L${PREFIX:-/data/data/com.termux/files/usr}/lib"
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install --no-cache-dir lxml
python3 -m pip install --no-cache-dir --upgrade yfinance

mkdir -p "$HOME/.termux/boot"
cp tools/boot.sh "$BOOT"
chmod 700 "$BOOT"
mkdir -p "$LOGDIR"

# Inicia explicitamente na interface de rede. Cloudflare continua usando a origem local,
# e o mesmo serviço passa a ser acessível pelo Tailscale em IP 100.x.x.x:8080.
# Não depende do pgrep do Termux:Boot para a primeira inicialização.
pkill -f '[p]ython3 flowcore.py serve' 2>/dev/null || true
export FLOWCORE__API__HOST="${FLOWCORE_BIND_HOST:-0.0.0.0}"
nohup python3 flowcore.py serve >> "$LOGDIR/flowcore.log" 2>&1 &
FLOWCORE_PID=$!
echo "FlowCore iniciado como PID $FLOWCORE_PID; aguardando confirmação interna..."

# O boot mantém cloudflared e bots persistentes. Se já estiver em execução, não cria duplicata.
if ! pgrep -f '[f]lowcore.sh' >/dev/null 2>&1; then
  nohup "$BOOT" >/dev/null 2>&1 &
fi

printf 'Validando inicialização do FlowCore...\n'
ready=0
for attempt in $(seq 1 12); do
  if curl -fsS --max-time 5 http://127.0.0.1:8080/api/health >/dev/null; then
    ready=1
    break
  fi
  if ! kill -0 "$FLOWCORE_PID" 2>/dev/null; then
    echo "ERRO: o processo FlowCore encerrou durante a inicialização." >&2
    tail -n 120 "$LOGDIR/flowcore.log" >&2 2>/dev/null || true
    exit 1
  fi
  sleep 2
done

if [ "$ready" -ne 1 ]; then
  echo "ERRO: FlowCore não respondeu após 24 segundos." >&2
  echo "--- PROCESSOS ---" >&2
  pgrep -af 'flowcore.py|flowcore.sh|cloudflared' >&2 || true
  echo "--- FLOWCORE LOG ---" >&2
  tail -n 100 "$HOME/.config/flowcore/flowcore.log" >&2 2>/dev/null || true
  echo "--- BOOT LOG ---" >&2
  tail -n 60 "$HOME/.config/flowcore/boot.log" >&2 2>/dev/null || true
  exit 1
fi

for path in /api/health /api/market/snapshot /api/market/overview /api/market/briefing /api/portfolios/moderate-ia-1m/summary; do
  code="$(curl -sS -o /tmp/flowcore-market-check.json -w '%{http_code}' --max-time 45 "http://127.0.0.1:8080${path}" || true)"
  printf '%s HTTP %s\n' "$path" "$code"
  if [ "$code" != "200" ]; then
    cat /tmp/flowcore-market-check.json 2>/dev/null || true
    exit 1
  fi
done

printf '\nFluxo FlowCore iniciado. Verificando o domínio público...\n'
public_code="$(curl -sS -o /tmp/flowcore-public-check.json -w '%{http_code}' --max-time 25 "$PUBLIC_URL/api/market/snapshot" || true)"
printf 'Cloudflare %s/api/market/snapshot HTTP %s\n' "$PUBLIC_URL" "$public_code"
if [ "$public_code" != "200" ]; then
  echo "O FlowCore está iniciado; o túnel pode levar alguns segundos para reconectar." >&2
  echo "Consulte: tail -n 60 $LOGDIR/cloudflared.log" >&2
fi
printf 'Acesso privado Tailscale: http://<IP-TAILSCALE-DO-TELEFONE>:8080/api/market/snapshot\n'
