#!/usr/bin/env bash
# FlowCore — Gerador de Relatório Final de Aprovação
# Coleta dados reais da máquina e imprime o relatório preenchido.
# Read-only: não altera nenhuma configuração.
#
# Uso:
#   chmod +x scripts/wsl/generate-report.sh
#   ./scripts/wsl/generate-report.sh
#   ./scripts/wsl/generate-report.sh | tee ~/AI/logs/relatorio-$(date +%Y-%m-%d).txt

set -euo pipefail

# ── helpers ──────────────────────────────────────────────────────────────────
val() { printf "%-12s: %s\n" "$1" "$2"; }
NA="N/A"

# ── coleta nvidia-smi ─────────────────────────────────────────────────────────
if command -v nvidia-smi &>/dev/null; then
    NV_NAME=$(nvidia-smi     --query-gpu=name             --format=csv,noheader,nounits 2>/dev/null | head -1 || echo "$NA")
    NV_DRIVER=$(nvidia-smi   --query-gpu=driver_version   --format=csv,noheader,nounits 2>/dev/null | head -1 || echo "$NA")
    NV_VRAM=$(nvidia-smi     --query-gpu=memory.total     --format=csv,noheader,nounits 2>/dev/null | head -1 || echo "$NA")
    NV_TEMP=$(nvidia-smi     --query-gpu=temperature.gpu  --format=csv,noheader,nounits 2>/dev/null | head -1 || echo "$NA")
    NV_UTIL=$(nvidia-smi     --query-gpu=utilization.gpu  --format=csv,noheader,nounits 2>/dev/null | head -1 || echo "$NA")
    NV_MEM_USED=$(nvidia-smi --query-gpu=memory.used      --format=csv,noheader,nounits 2>/dev/null | head -1 || echo "$NA")
    NV_POWER=$(nvidia-smi    --query-gpu=power.draw       --format=csv,noheader,nounits 2>/dev/null | head -1 || echo "$NA")
    NV_CUDA=$(nvidia-smi | grep -oP 'CUDA Version: \K[0-9.]+' 2>/dev/null || echo "$NA")

    # Thermal/Power Brake Slowdown (nvidia-smi -q)
    NV_Q=$(nvidia-smi -q 2>/dev/null || echo "")
    THERMAL_SD=$(echo "$NV_Q" | grep -i "Thermal Slowdown"    | head -1 | awk -F': ' '{print $2}' | tr -d ' \r' || echo "$NA")
    POWER_SD=$(echo  "$NV_Q" | grep -i "Power Brake Slowdown" | head -1 | awk -F': ' '{print $2}' | tr -d ' \r' || echo "$NA")
    HW_RECOV=$(echo  "$NV_Q" | grep -i "Hardware Recovery"    | head -1 | awk -F': ' '{print $2}' | tr -d ' \r' || echo "$NA")
    ARCH=$(echo      "$NV_Q" | grep -i "Architecture"         | head -1 | awk -F': ' '{print $2}' | tr -d ' \r' || echo "Ampere (RTX 30xx)")
    PCIE=$(echo      "$NV_Q" | grep -i "PCIe Generation"      | head -1 | awk -F': ' '{print $2}' | tr -d ' \r' || echo "$NA")
    ECC=$(echo       "$NV_Q" | grep -i "ECC Mode"             | head -1 | awk -F': ' '{print $2}' | tr -d ' \r' || echo "N/A (normal para GeForce)")

    NV_DETECTED="SIM"
else
    NV_NAME="nvidia-smi não encontrado"; NV_DRIVER="$NA"; NV_VRAM="$NA"
    NV_TEMP="$NA"; NV_UTIL="$NA"; NV_MEM_USED="$NA"; NV_POWER="$NA"; NV_CUDA="$NA"
    THERMAL_SD="$NA"; POWER_SD="$NA"; HW_RECOV="$NA"; ARCH="$NA"; PCIE="$NA"; ECC="$NA"
    NV_DETECTED="NÃO"
fi

# ── coleta sistema ────────────────────────────────────────────────────────────
KERNEL=$(uname -r)
DISTRO=$( (lsb_release -d 2>/dev/null | cut -f2) || echo "$NA")
HOSTNAME=$(hostname)

# ── WSL version (lê /proc/version ou uname -v) ───────────────────────────────
WSL_VER=$(uname -v 2>/dev/null | grep -oP 'Microsoft-Standard-WSL\K[0-9]+' || \
          cat /proc/version 2>/dev/null | grep -oP 'WSL\K[0-9]+' || echo "2")

# ── Python ───────────────────────────────────────────────────────────────────
PY_VER=$(python3 --version 2>/dev/null | awk '{print $2}' || echo "$NA")

if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    VENV_STATUS="ativo — $VIRTUAL_ENV"
elif [[ -d "$HOME/ai-env" ]]; then
    VENV_STATUS="existe (~/ai-env) — não ativo neste shell"
else
    VENV_STATUS="não encontrado"
fi

# ── PyTorch ──────────────────────────────────────────────────────────────────
PYTORCH_PY="${VIRTUAL_ENV:-}/bin/python3"
[[ ! -x "$PYTORCH_PY" ]] && PYTORCH_PY="$HOME/ai-env/bin/python3"
[[ ! -x "$PYTORCH_PY" ]] && PYTORCH_PY="python3"

PT_VER="$NA"; PT_CUDA="$NA"; PT_GPU="$NA"; PT_VRAM="$NA"; PT_TESTE="NÃO EXECUTADO"
if $PYTORCH_PY -c "import torch" &>/dev/null 2>&1; then
    PT_VER=$($PYTORCH_PY -c "import torch; print(torch.__version__)" 2>/dev/null || echo "$NA")
    CUDA_BOOL=$($PYTORCH_PY -c "import torch; print(torch.cuda.is_available())" 2>/dev/null || echo "False")
    if [[ "$CUDA_BOOL" == "True" ]]; then
        PT_CUDA="disponível"
        PT_GPU=$($PYTORCH_PY -c "import torch; print(torch.cuda.get_device_name(0))" 2>/dev/null || echo "$NA")
        PT_VRAM=$($PYTORCH_PY -c "import torch; p=torch.cuda.get_device_properties(0); print(round(p.total_memory/1024**3,2),'GB')" 2>/dev/null || echo "$NA")

        # Teste real de CUDA
        if $PYTORCH_PY - <<'PYEOF' &>/dev/null 2>&1
import torch, sys
x = torch.randn(4000, 4000, device='cuda')
y = torch.matmul(x, x)
torch.cuda.synchronize()
sys.exit(0)
PYEOF
        then
            PT_TESTE="APROVADO"
        else
            PT_TESTE="REPROVADO"
        fi
    else
        PT_CUDA="não disponível"
        PT_TESTE="REPROVADO (CUDA=False)"
    fi
else
    PT_VER="PyTorch não instalado"
fi

# ── Ollama ───────────────────────────────────────────────────────────────────
OL_VER="$NA"; OL_SERVICE="$NA"; OL_GPU="$NA"; OL_TEST="NÃO EXECUTADO"
if command -v ollama &>/dev/null; then
    OL_VER=$(ollama --version 2>/dev/null || echo "$NA")
    if systemctl is-active --quiet ollama 2>/dev/null; then
        OL_SERVICE="ativo (systemd)"
    else
        # Testa se o server responde
        if curl -sf http://localhost:11434/api/tags &>/dev/null; then
            OL_SERVICE="ativo (processo manual)"
        else
            OL_SERVICE="inativo"
        fi
    fi

    # Verifica se há modelo baixado e testa
    MODELS=$(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}' | head -5 || echo "")
    if echo "$MODELS" | grep -qi "qwen3"; then
        OL_TEST="qwen3 disponível (pronto para teste interativo)"
        # Verifica uso de GPU via nvidia-smi após breve query
        if command -v nvidia-smi &>/dev/null; then
            GPU_MEM_BEFORE=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)
            echo "qwen3:8b" | timeout 10 ollama run qwen3:8b "Responda em uma palavra: qual é 2+2?" &>/dev/null || true
            GPU_MEM_AFTER=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)
            if [[ "$GPU_MEM_AFTER" -gt "$GPU_MEM_BEFORE" ]] 2>/dev/null; then
                OL_GPU="RTX 3060 (VRAM aumentou durante inferência)"
                OL_TEST="APROVADO (qwen3:8b rodou na GPU)"
            else
                OL_GPU="não confirmado automaticamente — verifique manualmente com: ollama run qwen3:8b"
                OL_TEST="PENDENTE — execute: ollama run qwen3:8b"
            fi
        fi
    elif [[ -n "$MODELS" ]]; then
        OL_TEST="modelos presentes: $MODELS — qwen3:8b não baixado ainda"
        OL_GPU="não testado"
    else
        OL_TEST="nenhum modelo baixado — execute: ollama run qwen3:8b"
        OL_GPU="não testado"
    fi
else
    OL_VER="não instalado"; OL_SERVICE="N/A"; OL_GPU="N/A"; OL_TEST="NÃO INSTALADO"
fi

# ── Docker ───────────────────────────────────────────────────────────────────
DOCKER_VER="$NA"; DOCKER_STATUS="$NA"
if command -v docker &>/dev/null; then
    DOCKER_VER=$(docker --version 2>/dev/null | awk '{print $3}' | tr -d ',' || echo "$NA")
    if docker info &>/dev/null 2>&1; then
        DOCKER_STATUS="funcionando"
    else
        DOCKER_STATUS="instalado mas daemon inacessível (inicie o Docker Desktop no Windows)"
    fi
else
    DOCKER_VER="não instalado"
    DOCKER_STATUS="não instalado"
fi

# ── Classificação final ───────────────────────────────────────────────────────
RESULTADO="APROVADA PARA IA LOCAL"
RESSALVAS=""

[[ "$NV_DETECTED" == "NÃO" ]] && { RESULTADO="NÃO APROVADA"; RESSALVAS+=" [GPU não detectada no WSL]"; }
[[ "$PT_TESTE" == "REPROVADO"* ]] && { RESULTADO="NÃO APROVADA"; RESSALVAS+=" [PyTorch CUDA falhou]"; }
[[ "$PT_VER" == "PyTorch não instalado" ]] && { RESULTADO="NÃO APROVADA"; RESSALVAS+=" [PyTorch não instalado]"; }
[[ "$OL_VER" == "não instalado" ]] && { [[ "$RESULTADO" == "APROVADA PARA IA LOCAL" ]] && RESULTADO="APROVADA COM RESSALVAS"; RESSALVAS+=" [Ollama não instalado]"; }
[[ "$OL_TEST" == "PENDENTE"* || "$OL_TEST" == "nenhum"* || "$OL_TEST" == "modelos"* ]] && {
    [[ "$RESULTADO" == "APROVADA PARA IA LOCAL" ]] && RESULTADO="APROVADA COM RESSALVAS"
    RESSALVAS+=" [Ollama não testado com GPU]"
}
[[ "$DOCKER_STATUS" == "não instalado" ]] && {
    [[ "$RESULTADO" == "APROVADA PARA IA LOCAL" ]] && RESULTADO="APROVADA COM RESSALVAS"
    RESSALVAS+=" [Docker não instalado]"
}

# ── impressão do relatório ────────────────────────────────────────────────────
cat <<REPORT

╔══════════════════════════════════════════════════════════════════════════════╗
║          RELATÓRIO FINAL — MÁQUINA IA LOCAL (FlowCore)                     ║
║          Gerado em: $(date '+%Y-%m-%d %H:%M:%S')                                   ║
╚══════════════════════════════════════════════════════════════════════════════╝

── HARDWARE ──────────────────────────────────────────────────────────────────
$(val "CPU"       "AMD Ryzen 7 5700X")
$(val "RAM"       "32 GB DDR4")
$(val "GPU"       "$NV_NAME")
$(val "VRAM"      "${NV_VRAM} MiB")
$(val "SSD"       "NVMe (verifique no Windows: systeminfo ou Gerenciador de Discos)")
$(val "OS"        "$DISTRO (WSL) — Windows 11")

── NVIDIA ────────────────────────────────────────────────────────────────────
$(val "Modelo"    "$NV_NAME")
$(val "Driver"    "$NV_DRIVER")
$(val "CUDA sup." "$NV_CUDA")
$(val "Arquitet." "$ARCH")
$(val "PCIe"      "$PCIE")
$(val "Temp idle" "${NV_TEMP} °C")
$(val "Consumo"   "${NV_POWER} W")
$(val "Utilizacao" "${NV_UTIL} %")
$(val "VRAM usada" "${NV_MEM_USED} MiB")
$(val "ECC"       "$ECC")
$(val "Therm. SD" "${THERMAL_SD:-N/A}")
$(val "Power SD"  "${POWER_SD:-N/A}")
$(val "HW Recov." "${HW_RECOV:-N/A}")
$(val "GPU no WSL" "$NV_DETECTED")

── WSL ───────────────────────────────────────────────────────────────────────
$(val "Versão"    "WSL $WSL_VER")
$(val "Distro"    "$DISTRO")
$(val "Kernel"    "$KERNEL")
$(val "Hostname"  "$HOSTNAME")
$(val "GPU WSL"   "$NV_DETECTED")

── PYTHON ────────────────────────────────────────────────────────────────────
$(val "Versão"    "$PY_VER")
$(val "venv"      "$VENV_STATUS")

── PYTORCH ───────────────────────────────────────────────────────────────────
$(val "Versão"    "$PT_VER")
$(val "CUDA"      "$PT_CUDA")
$(val "GPU"       "$PT_GPU")
$(val "VRAM"      "$PT_VRAM")
$(val "Teste CUDA" "$PT_TESTE")

── OLLAMA ────────────────────────────────────────────────────────────────────
$(val "Versão"    "$OL_VER")
$(val "Serviço"   "$OL_SERVICE")
$(val "GPU"       "$OL_GPU")
$(val "Teste"     "$OL_TEST")

── DOCKER ────────────────────────────────────────────────────────────────────
$(val "Versão"    "$DOCKER_VER")
$(val "Estado"    "$DOCKER_STATUS")

══════════════════════════════════════════════════════════════════════════════
  RESULTADO FINAL: $RESULTADO
$([ -n "$RESSALVAS" ] && echo "  Ressalvas: $RESSALVAS" || true)
══════════════════════════════════════════════════════════════════════════════

REPORT
