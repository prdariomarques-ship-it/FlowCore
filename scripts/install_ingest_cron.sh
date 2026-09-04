#!/usr/bin/env bash
# Instala o job de ingestão contínua dos observers no cron do sistema.
#
# Uso (na máquina onde o FlowCore roda — WSL/Termux/Linux):
#   bash scripts/install_ingest_cron.sh          # cron por hora
#   bash scripts/install_ingest_cron.sh --every 5m
#
# Idempotente: remove entry anterior e instala a nova.
# Não destrói nenhum outro job do crontab do usuário.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON="$(command -v python3)"
ENTRY_PREFIX="flowcore_ingest_observers"
CRON_LOG="$ROOT_DIR/logs/ingest_cron.log"
mkdir -p "$ROOT_DIR/logs"

if [ "$PYTHON" = "" ]; then
    echo "ERRO: python3 não encontrado no PATH."
    exit 1
fi

case "${2:-h}" in
    1m) SCHEDULE="* * * * *" ;;
    5m) SCHEDULE="*/5 * * * *" ;;
    15m) SCHEDULE="*/15 * * * *" ;;
    30m) SCHEDULE="*/30 * * * *" ;;
    h) SCHEDULE="0 * * * *" ;;
    *) echo "Uso: $0 [--every 1m|5m|15m|30m|h]"; exit 1 ;;
esac

NEW_ENTRY="$SCHEDULE $PYTHON $SCRIPT_DIR/ingest_observers.py >> $CRON_LOG 2>&1"

EXISTING="$(crontab -l 2>/dev/null | grep -v "$ENTRY_PREFIX" || true)"
( [ -n "$EXISTING" ] && echo "$EXISTING"; echo "# $ENTRY_PREFIX — fluxo financeiro FlowCore (Sprint 19+)"; echo "$NEW_ENTRY" ) | crontab -

echo "✓ Job de ingestão instalado no cron do sistema:"
crontab -l | grep -A1 "$ENTRY_PREFIX"
echo ""
echo "Verificação manual: python3 $SCRIPT_DIR/ingest_observers.py"
echo "Status das execuções: $ROOT_DIR/logs/ingest_job.jsonl"
echo "Histórico real: python3 $ROOT_DIR/flowcore.py observer events"
