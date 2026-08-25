#!/usr/bin/env bash
# Gera o APK do FlowCore Mobile via EAS Build (cloud Expo)
# Pré-requisito: Node.js, pnpm, eas-cli instalados e conta expo.dev
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$SCRIPT_DIR/flowcore-mobile"

echo "=== FlowCore Mobile — Build APK ==="
echo ""

# Verificar dependências
command -v node  >/dev/null 2>&1 || { echo "[ERRO] Node.js não encontrado. Instale em https://nodejs.org"; exit 1; }
command -v pnpm  >/dev/null 2>&1 || { npm install -g pnpm; }
command -v eas   >/dev/null 2>&1 || { npm install -g eas-cli; }

echo "[1/4] Login na Expo (se ainda não estiver logado)..."
eas whoami 2>/dev/null || eas login

echo ""
echo "[2/4] Instalando dependências..."
cd "$APP_DIR"
pnpm install --frozen-lockfile

echo ""
echo "[3/4] Iniciando build Android (perfil: preview → APK)..."
eas build --platform android --profile preview --non-interactive

echo ""
echo "[4/4] Build enviado para a nuvem EAS."
echo "      Acompanhe em: https://expo.dev/accounts/[seu-usuario]/projects/flowcore-mobile/builds"
echo ""
echo "Quando concluir (~10 min), baixe o .apk pelo link acima"
echo "e instale com: adb install flowcore-mobile.apk"
echo "ou transfira direto para o Android e abra o arquivo."
