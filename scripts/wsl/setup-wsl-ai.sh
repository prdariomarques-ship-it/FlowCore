#!/usr/bin/env bash
# FlowCore — WSL AI Environment Setup
# Idempotent: safe to re-run. Installs only what is missing.
# Run inside Ubuntu/WSL as your regular user (sudo will be requested where needed).

set -euo pipefail

RESET='\033[0m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'

section() { echo -e "\n${CYAN}>>> $* ${RESET}"; }
ok()      { echo -e "${GREEN}✓${RESET} $*"; }
warn()    { echo -e "${YELLOW}!${RESET} $*"; }
fail()    { echo -e "${RED}✗${RESET} $*"; exit 1; }
already() { echo -e "${GREEN}já instalado${RESET}: $*"; }

# ──────────────────────────────────────────────
# ETAPA 1 — Verificar GPU no WSL
# ──────────────────────────────────────────────
section "ETAPA 1 — Verificar GPU (nvidia-smi)"
if command -v nvidia-smi &>/dev/null; then
    nvidia-smi --query-gpu=name,driver_version,memory.total \
        --format=csv,noheader,nounits
    ok "GPU detectada no WSL"
else
    fail "nvidia-smi nao encontrado. Verifique se o driver NVIDIA do Windows esta instalado e se o WSL2 esta na versao correta (wsl --version)."
fi

# ──────────────────────────────────────────────
# ETAPA 2 — Atualizar sistema
# ──────────────────────────────────────────────
section "ETAPA 2 — Atualizar pacotes do sistema"
sudo apt-get update -y
sudo apt-get upgrade -y
ok "Sistema atualizado"

# ──────────────────────────────────────────────
# ETAPA 3 — Ferramentas base
# ──────────────────────────────────────────────
section "ETAPA 3 — Ferramentas base"
PKGS=(curl wget git build-essential python3 python3-pip python3-venv python3-dev cmake pkg-config unzip htop)
MISSING=()
for pkg in "${PKGS[@]}"; do
    if dpkg -s "$pkg" &>/dev/null 2>&1; then
        already "$pkg"
    else
        MISSING+=("$pkg")
    fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
    sudo apt-get install -y "${MISSING[@]}"
    ok "Instalados: ${MISSING[*]}"
fi

# nvtop separado (pode nao existir em repos antigos)
if ! command -v nvtop &>/dev/null; then
    sudo apt-get install -y nvtop 2>/dev/null && ok "nvtop instalado" || warn "nvtop nao disponivel neste repositorio (nao critico)"
else
    already "nvtop"
fi

python3 --version
pip3 --version
git --version

# ──────────────────────────────────────────────
# ETAPA 4 — Ambiente virtual Python
# ──────────────────────────────────────────────
section "ETAPA 4 — Ambiente virtual Python (~/ai-env)"
if [[ -d "$HOME/ai-env" ]]; then
    already "~/ai-env"
else
    python3 -m venv "$HOME/ai-env"
    ok "venv criado em ~/ai-env"
fi

# Ativar para o restante do script
# shellcheck disable=SC1091
source "$HOME/ai-env/bin/activate"
python -m pip install --upgrade pip setuptools wheel
ok "pip/setuptools/wheel atualizados"

# ──────────────────────────────────────────────
# ETAPA 5 — PyTorch com CUDA
# ──────────────────────────────────────────────
section "ETAPA 5 — PyTorch com CUDA"

if python -c "import torch" &>/dev/null 2>&1; then
    PT_VER=$(python -c "import torch; print(torch.__version__)" 2>/dev/null)
    CUDA_OK=$(python -c "import torch; print(torch.cuda.is_available())" 2>/dev/null)
    already "PyTorch $PT_VER (CUDA: $CUDA_OK)"
    if [[ "$CUDA_OK" != "True" ]]; then
        warn "PyTorch instalado mas CUDA nao disponivel. Considere reinstalar com suporte CUDA."
        warn "Execute: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128"
    fi
else
    # Instala PyTorch com CUDA 12.8 (compativel com drivers recentes e RTX 3060)
    echo "Instalando PyTorch com CUDA 12.8..."
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
    ok "PyTorch instalado"
fi

# ──────────────────────────────────────────────
# ETAPA 6 — Teste PyTorch CUDA
# ──────────────────────────────────────────────
section "ETAPA 6 — Teste PyTorch + CUDA"
python - <<'PYEOF'
import torch
print(f"PyTorch : {torch.__version__}")
print(f"CUDA    : {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU     : {torch.cuda.get_device_name(0)}")
    p = torch.cuda.get_device_properties(0)
    print(f"VRAM    : {round(p.total_memory/1024**3, 2)} GB")

    x = torch.randn(4000, 4000, device='cuda')
    y = torch.matmul(x, x)
    torch.cuda.synchronize()
    print("CUDA TESTE: OK")
else:
    print("CUDA TESTE: FALHOU — GPU nao detectada pelo PyTorch")
PYEOF

# ──────────────────────────────────────────────
# ETAPA 7 — Instalar Ollama
# ──────────────────────────────────────────────
section "ETAPA 7 — Ollama"
if command -v ollama &>/dev/null; then
    already "$(ollama --version 2>/dev/null || echo ollama)"
else
    curl -fsSL https://ollama.com/install.sh | sh
    ok "Ollama instalado"
fi

# Garantir servico
if systemctl is-active --quiet ollama 2>/dev/null; then
    ok "Servico ollama ja ativo"
else
    sudo systemctl enable --now ollama 2>/dev/null && ok "Servico ollama ativado" || \
        warn "systemctl nao disponivel (WSL sem systemd?). Inicie manualmente: ollama serve &"
fi

ollama --version

# ──────────────────────────────────────────────
# ETAPA 8 — Estrutura de diretorios ~/AI
# ──────────────────────────────────────────────
section "ETAPA 8 — Estrutura ~/AI"
for dir in ~/AI ~/AI/models ~/AI/projects ~/AI/data ~/AI/notebooks ~/AI/scripts ~/AI/docker ~/AI/logs; do
    mkdir -p "$dir"
done
ok "Diretorios ~/AI criados"

# ──────────────────────────────────────────────
# ETAPA 9 — Instalar scripts de diagnóstico
# ──────────────────────────────────────────────
section "ETAPA 9 — Scripts de diagnóstico"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for SCRIPT_NAME in gpu-check.sh generate-report.sh; do
    SRC="$SCRIPT_DIR/$SCRIPT_NAME"
    DST="$HOME/AI/scripts/$SCRIPT_NAME"
    if [[ -f "$SRC" ]]; then
        cp "$SRC" "$DST"
        chmod +x "$DST"
        ok "$SCRIPT_NAME instalado em ~/AI/scripts/"
    else
        warn "$SCRIPT_NAME nao encontrado em $SCRIPT_DIR — copie-o manualmente para ~/AI/scripts/"
    fi
done

# ──────────────────────────────────────────────
# ETAPA 10 — Docker (verificacao apenas)
# ──────────────────────────────────────────────
section "ETAPA 10 — Docker"
if command -v docker &>/dev/null; then
    ok "$(docker --version)"
    warn "Docker encontrado. Certifique-se de que a integracao WSL2 esta ativa no Docker Desktop (Settings > Resources > WSL Integration)."
else
    warn "Docker nao encontrado. Instale o Docker Desktop no Windows e ative a integracao WSL2."
    warn "Referencia: https://docs.docker.com/desktop/wsl/"
fi

# ──────────────────────────────────────────────
# FIM
# ──────────────────────────────────────────────
section "Setup concluido"
echo ""
echo "Proximos passos:"
echo "  1. Diagnostico resumido:            ~/AI/scripts/gpu-check.sh"
echo "  2. Relatorio final preenchido:      ~/AI/scripts/generate-report.sh"
echo "     (salvar em arquivo:              ~/AI/scripts/generate-report.sh | tee ~/AI/logs/relatorio-\$(date +%Y-%m-%d).txt)"
echo "  3. Teste Ollama com GPU:            ollama run qwen3:8b"
echo "     (monitore em outro terminal:      watch -n 1 nvidia-smi)"
echo "  4. Para ativar o venv em novas sessoes: source ~/ai-env/bin/activate"
echo ""
