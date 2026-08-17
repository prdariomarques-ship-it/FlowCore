#!/usr/bin/env bash
# Instala o job de broadcast Telegram (Dario OS + B3/Ibovespa) no cron do sistema.
#
# Uso (na máquina onde o FlowCore roda — WSL/Termux/Linux):
#   bash scripts/install_telegram_cron.sh              # a cada 30 min
#   bash scripts/install_telegram_cron.sh --every 15m
#
# O script alvo já se auto-limita ao pregão B3 (seg-sex 10h-18h BRT) —
# fora desse horário o cron dispara e o job não faz nada (no-op).
# Idempotente: remove entry anterior e instala a nova.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON="$(command -v python3)"
ENTRY_PREFIX="flowcore_telegram_broadcast"
CRON_LOG="$ROOT_DIR/logs/telegram_broadcast_cron.log"
mkdir -p "$ROOT_DIR/logs"

if [ "$PYTHON" = "" ]; then
    echo "ERRO: python3 não encontrado no PATH."
    exit 1
fi

case "${2:-30m}" in
    5m) SCHEDULE="*/5 * * * *" ;;
    15m) SCHEDULE="*/15 * * * *" ;;
    30m) SCHEDULE="*/30 * * * *" ;;
    h) SCHEDULE="0 * * * *" ;;
    *) echo "Uso: $0 [--every 5m|15m|30m|h]"; exit 1 ;;
esac

NEW_ENTRY="$SCHEDULE $PYTHON $SCRIPT_DIR/telegram_broadcast.py >> $CRON_LOG 2>&1"

EXISTING="$(crontab -l 2>/dev/null | grep -v "$ENTRY_PREFIX" || true)"
( [ -n "$EXISTING" ] && echo "$EXISTING"; echo "# $ENTRY_PREFIX — Dario OS + B3/Ibovespa via Telegram"; echo "$NEW_ENTRY" ) | crontab -

echo "✓ Job de broadcast Telegram instalado no cron do sistema:"
crontab -l | grep -A1 "$ENTRY_PREFIX"
echo ""
echo "Verificação manual: python3 $SCRIPT_DIR/telegram_broadcast.py"
echo "Log de execuções:   $ROOT_DIR/logs/telegram_broadcast.jsonl"
echo "Log bruto do cron:  $CRON_LOG"
