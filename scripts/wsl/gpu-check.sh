#!/usr/bin/env bash
# FlowCore — GPU Diagnostic Script
# Read-only: displays system and GPU status without changing any configuration.
# Place at: ~/AI/scripts/gpu-check.sh
# Usage: chmod +x ~/AI/scripts/gpu-check.sh && ~/AI/scripts/gpu-check.sh

set -euo pipefail

RESET='\033[0m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'

section() { echo -e "\n${CYAN}=== $* ===${RESET}"; }
ok()      { echo -e "${GREEN}OK${RESET}  $*"; }
warn()    { echo -e "${YELLOW}AVISO${RESET}  $*"; }
fail()    { echo -e "${RED}ERRO${RESET}  $*"; }

section "FlowCore GPU Check — $(date '+%Y-%m-%d %H:%M:%S')"

# --- System ---
section "Sistema"
echo "Hostname : $(hostname)"
echo "Kernel   : $(uname -r)"
if command -v lsb_release &>/dev/null; then
    echo "Distro   : $(lsb_release -d | cut -f2)"
fi

# --- Python ---
section "Python"
if command -v python3 &>/dev/null; then
    PY_VER=$(python3 --version 2>&1)
    ok "$PY_VER"
else
    fail "python3 nao encontrado"
fi

if command -v pip3 &>/dev/null; then
    PIP_VER=$(pip3 --version 2>&1 | awk '{print $1" "$2}')
    ok "pip $PIP_VER"
fi

# --- Virtual env ---
section "Ambiente Virtual"
if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    ok "Ativo: $VIRTUAL_ENV"
elif [[ -f "$HOME/ai-env/bin/activate" ]]; then
    warn "ai-env existe mas nao esta ativo. Execute: source ~/ai-env/bin/activate"
else
    warn "Nenhum venv detectado em ~/ai-env"
fi

# --- GPU via nvidia-smi ---
section "NVIDIA GPU"
if command -v nvidia-smi &>/dev/null; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader,nounits 2>/dev/null | head -1)
    DRIVER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader,nounits 2>/dev/null | head -1)
    CUDA_VER=$(nvidia-smi --query-gpu=cuda_version --format=csv,noheader,nounits 2>/dev/null | head -1 || \
               nvidia-smi | grep -oP 'CUDA Version: \K[0-9.]+' || echo "N/A")
    VRAM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1)
    TEMP=$(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits 2>/dev/null | head -1)
    UTIL=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | head -1)
    MEM_USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)
    POWER=$(nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits 2>/dev/null | head -1 || echo "N/A")

    ok "GPU       : $GPU_NAME"
    ok "Driver    : $DRIVER"
    ok "CUDA sup. : $CUDA_VER"
    ok "VRAM      : $VRAM MiB"
    ok "Temp      : ${TEMP} C"
    ok "Utilizacao: ${UTIL} %"
    ok "VRAM usada: ${MEM_USED} MiB"
    ok "Consumo   : ${POWER} W"
else
    fail "nvidia-smi nao encontrado — GPU nao acessivel no WSL"
fi

# --- PyTorch ---
section "PyTorch"
PYTORCH_PY="${VIRTUAL_ENV:-}/bin/python3"
[[ ! -x "$PYTORCH_PY" ]] && PYTORCH_PY="python3"

if $PYTORCH_PY -c "import torch" &>/dev/null 2>&1; then
    PT_VER=$($PYTORCH_PY -c "import torch; print(torch.__version__)" 2>/dev/null)
    CUDA_AVAIL=$($PYTORCH_PY -c "import torch; print(torch.cuda.is_available())" 2>/dev/null)
    ok "Versao    : $PT_VER"
    if [[ "$CUDA_AVAIL" == "True" ]]; then
        GPU_TORCH=$($PYTORCH_PY -c "import torch; print(torch.cuda.get_device_name(0))" 2>/dev/null)
        VRAM_TORCH=$($PYTORCH_PY -c "import torch; p=torch.cuda.get_device_properties(0); print(round(p.total_memory/1024**3,2))" 2>/dev/null)
        ok "CUDA      : disponivel"
        ok "GPU       : $GPU_TORCH"
        ok "VRAM      : $VRAM_TORCH GB"
    else
        fail "CUDA nao disponivel no PyTorch"
    fi
else
    warn "PyTorch nao instalado (ou nao ativo no venv atual)"
fi

# --- Ollama ---
section "Ollama"
if command -v ollama &>/dev/null; then
    OL_VER=$(ollama --version 2>/dev/null || echo "desconhecido")
    ok "Versao: $OL_VER"
    if systemctl is-active --quiet ollama 2>/dev/null; then
        ok "Servico: ativo"
    else
        warn "Servico ollama nao esta ativo (systemctl)"
    fi
else
    warn "Ollama nao encontrado"
fi

# --- Docker ---
section "Docker"
if command -v docker &>/dev/null; then
    ok "$(docker --version 2>/dev/null)"
else
    warn "Docker nao encontrado"
fi

section "Diagnostico concluido"
