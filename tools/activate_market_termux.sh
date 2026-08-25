#!/data/data/com.termux/files/usr/bin/bash
# Atualiza a camada de mercado e comprova a API local do FlowCore no Termux.
# Não grava tokens nem modifica a configuração privada do Cloudflare/Telegram.

set -eu

BASE="$HOME/FlowCore"
BRANCH="claude/flowcore-architecture-consolidation-h95fi2"
BOOT="$HOME/.termux/boot/flowcore.sh"

if [ ! -d "$BASE/.git" ]; then
  echo "ERRO: repositório FlowCore não encontrado em $BASE" >&2
  exit 1
fi

cd "$BASE"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

python3 -m pip install --upgrade yfinance

mkdir -p "$HOME/.termux/boot"
cp tools/boot.sh "$BOOT"
chmod 700 "$BOOT"

# O loop de boot reconhece a ausência do processo e recria FlowCore com o código novo.
pkill -f '[p]ython3 flowcore.py serve' 2>/dev/null || true

# Se o Termux:Boot ainda não estiver ativo nesta sessão, iniciar o mesmo script manualmente.
if ! pgrep -f '[f]lowcore.sh' >/dev/null 2>&1; then
  nohup "$BOOT" >/dev/null 2>&1 &
fi

printf 'Aguardando FlowCore atualizado...\n'
for attempt in $(seq 1 24); do
  if curl -fsS --max-time 5 http://127.0.0.1:8080/api/health >/dev/null; then
    break
  fi
  sleep 5
done

for path in /api/health /api/market/overview /api/market/briefing /api/portfolios/moderate-ia-1m/summary; do
  code="$(curl -sS -o /tmp/flowcore-market-check.json -w '%{http_code}' --max-time 45 "http://127.0.0.1:8080${path}" || true)"
  printf '%s HTTP %s\n' "$path" "$code"
  if [ "$code" != "200" ]; then
    cat /tmp/flowcore-market-check.json 2>/dev/null || true
    exit 1
  fi
done

printf '\nFluxo local pronto. Agora confira o domínio público:\n'
printf 'curl -s https://flowcore.admissaoazusa.com.br/api/market/overview\n'
