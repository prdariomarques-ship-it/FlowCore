#!/usr/bin/env bash
# Gera o APK do FlowCore Mobile via EAS Build (cloud Expo)
#
# USO COM TOKEN (recomendado — sem login interativo):
#   export EXPO_TOKEN=<seu-token>
#   bash mobile/build-apk.sh
#
# Gere o token em: https://expo.dev/accounts/dmn0712/settings/access-tokens
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$SCRIPT_DIR/flowcore-mobile"

echo "=== FlowCore Mobile — Build APK (dmn0712) ==="
echo ""

# Verificar dependências
command -v node >/dev/null 2>&1 || { echo "[ERRO] Node.js não encontrado. Instale em https://nodejs.org"; exit 1; }
command -v pnpm >/dev/null 2>&1 || npm install -g pnpm
command -v eas  >/dev/null 2>&1 || npm install -g eas-cli

# Autenticação via token (preferencial) ou login interativo
if [ -n "${EXPO_TOKEN:-}" ]; then
  echo "[auth] Usando EXPO_TOKEN (não-interativo)"
else
  echo "[auth] EXPO_TOKEN não definido — tentando login interativo..."
  eas whoami 2>/dev/null || eas login
fi

echo ""
echo "[1/3] Instalando dependências..."
cd "$APP_DIR"
pnpm install --frozen-lockfile

echo ""
echo "[2/3] Iniciando build Android (perfil: preview → APK)..."
eas build \
  --platform android \
  --profile preview \
  --non-interactive

echo ""
echo "[3/3] Build enviado para a nuvem EAS."
echo "      Acompanhe em: https://expo.dev/accounts/dmn0712/projects/flowcore-mobile/builds"
echo ""
echo "Quando concluir (~10 min), baixe o .apk pelo link acima"
echo "e instale no Android: adb install flowcore-mobile.apk"
echo "ou transfira o arquivo direto para o celular e abra."
