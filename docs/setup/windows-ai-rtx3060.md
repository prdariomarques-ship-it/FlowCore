# Configuração: Máquina Windows para IA Local com RTX 3060

**Hardware alvo**

| Componente | Especificação |
|---|---|
| CPU | AMD Ryzen 7 5700X |
| GPU | NVIDIA GeForce RTX 3060 12 GB |
| RAM | 32 GB DDR4 |
| SSD | NVMe 500 GB ou superior |
| OS | Windows 11 |

**Objetivo:** ambiente funcional e verificável para Ollama, LLMs locais, PyTorch com CUDA, Python, WSL2 e Docker.

**Regra principal:** verificar antes de instalar. Não substituir o que já funciona.

---

## Etapa 1 — Diagnóstico inicial do Windows

Abra o **PowerShell como Administrador** e execute o script de diagnóstico incluído neste repositório:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\windows\diagnose-windows.ps1
```

Ou execute manualmente:

```powershell
systeminfo
wsl --status
wsl --version
wsl -l -v
nvidia-smi
```

**Confirme:**
- Windows 11 instalado
- GPU NVIDIA RTX 3060 (~12 GB VRAM)
- Versão do driver NVIDIA
- Versão CUDA reportada pelo driver

> Não altere o driver se `nvidia-smi` já funcionar e mostrar a GPU corretamente.

---

## Etapa 2 — WSL2

### Verificar se já está instalado

```powershell
wsl -l -v
```

Se o Ubuntu aparecer com `VERSION 2`, o WSL2 já está configurado. **Pule para a Etapa 3.**

### Instalar (se necessário)

```powershell
wsl --install
```

Reinicie quando solicitado. Após reiniciar:

```powershell
wsl -l -v
```

Confirme que o Ubuntu está com `VERSION 2`. Se estiver com versão 1:

```powershell
wsl --set-version Ubuntu 2
```

---

## Etapa 3 — Preparar Ubuntu/WSL

Abra o terminal Ubuntu e execute:

### Opção A — Script automatizado (recomendado)

Clone ou copie o script para dentro do WSL e execute:

```bash
chmod +x scripts/wsl/setup-wsl-ai.sh
./scripts/wsl/setup-wsl-ai.sh
```

O script é idempotente: verifica o que já existe antes de instalar.

### Opção B — Manual

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y curl wget git build-essential python3 python3-pip python3-venv python3-dev
```

Verifique:

```bash
python3 --version
pip3 --version
git --version
```

---

## Etapa 4 — Verificar GPU dentro do WSL

```bash
nvidia-smi
```

**Saída esperada:**

```
+-----------------------------------------------------------------------------+
| NVIDIA-SMI ...   Driver Version: ...   CUDA Version: ...                    |
|-------------------------------+----------------------+----------------------|
| GeForce RTX 3060              | ...                  |                      |
|  12288 MiB / 12288 MiB        |                      |                      |
+-----------------------------------------------------------------------------+
```

**Campos normais para RTX 3060:**
- `ECC: N/A` — correto para GPUs GeForce (sem ECC de hardware)
- Thermal Slowdown: Off
- Power Brake Slowdown: Off

Se `nvidia-smi` não funcionar dentro do WSL, o driver do Windows pode estar desatualizado ou o WSL não está na versão correta. Verifique com `wsl --version` (requer WSL 2.x+).

---

## Etapa 5 — Ambiente virtual Python

```bash
python3 -m venv ~/ai-env
source ~/ai-env/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

Não instale pacotes de IA globalmente. Use sempre o venv.

Adicione ao `~/.bashrc` para ativar automaticamente (opcional):

```bash
echo 'source ~/ai-env/bin/activate' >> ~/.bashrc
```

---

## Etapa 6 — PyTorch com CUDA

Com o venv ativo:

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```

> A URL `cu128` corresponde ao CUDA 12.8. Se seu driver suportar apenas CUDA 12.1, use `cu121`.
> Consulte: https://pytorch.org/get-started/locally/

### Verificação básica

```bash
python -c "
import torch
print('PyTorch:', torch.__version__)
print('CUDA:', torch.cuda.is_available())
print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NÃO DETECTADA')
vram = torch.cuda.get_device_properties(0).total_memory/1024**3 if torch.cuda.is_available() else 0
print('VRAM:', round(vram, 2), 'GB')
"
```

**Resultado esperado:**
```
PyTorch: 2.x.x+cu128
CUDA: True
GPU: NVIDIA GeForce RTX 3060
VRAM: 11.99 GB
```

---

## Etapa 7 — Teste real de CUDA

```bash
python -c "
import torch
print('PyTorch:', torch.__version__)
print('CUDA:', torch.cuda.is_available())
print('GPU:', torch.cuda.get_device_name(0))
x = torch.randn(5000, 5000, device='cuda')
y = torch.matmul(x, x)
torch.cuda.synchronize()
print('CUDA TESTE: OK')
"
```

Enquanto roda, monitore em outro terminal:

```bash
watch -n 1 nvidia-smi
```

**Confirme:**
- Utilização da GPU sobe durante o cálculo
- VRAM aumenta
- Temperatura sobe moderadamente e estabiliza
- Nenhum erro

---

## Etapa 8 — Ollama

### Verificar se já está instalado

```bash
ollama --version
```

### Instalar (se necessário)

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Garantir o serviço

```bash
sudo systemctl enable --now ollama
systemctl status ollama --no-pager
```

Se o WSL não tiver systemd habilitado, inicie manualmente:

```bash
ollama serve &
```

---

## Etapa 9 — Teste Ollama com GPU

```bash
ollama run qwen3:8b
```

Faça uma pergunta simples. O modelo deve responder normalmente.

Em outro terminal:

```bash
watch -n 1 nvidia-smi
```

**Confirme:**
- VRAM em uso aumenta (~5-8 GB para qwen3:8b)
- Utilização da GPU sobe durante a geração de tokens
- Resposta normal do modelo

> Não baixe modelos maiores que 8B sem verificar o espaço disponível em disco.
> `df -h ~` para verificar.

---

## Etapa 10 — Ferramentas de desenvolvimento

```bash
sudo apt install -y build-essential cmake pkg-config unzip htop nvtop
```

Monitor da GPU no terminal:

```bash
nvtop
```

---

## Etapa 11 — Docker

### Verificar se já está instalado

```bash
docker --version
```

### Se não estiver instalado

Instale o **Docker Desktop** no Windows:
https://docs.docker.com/desktop/install/windows-install/

Nas configurações do Docker Desktop:
- Settings → General → **Use the WSL 2 based engine** ✓
- Settings → Resources → WSL Integration → ativar sua distribuição Ubuntu

Após configurar, verifique dentro do WSL:

```bash
docker run --rm hello-world
```

> Não instale componentes NVIDIA adicionais para Docker se a aceleração CUDA já estiver funcionando via PyTorch/Ollama.

---

## Etapa 12 — Estrutura de diretórios

```bash
mkdir -p ~/AI/{models,projects,data,notebooks,scripts,docker,logs}
```

---

## Etapa 13 — Script de diagnóstico

Copie o `gpu-check.sh` deste repositório:

```bash
cp scripts/wsl/gpu-check.sh ~/AI/scripts/gpu-check.sh
chmod +x ~/AI/scripts/gpu-check.sh
```

Execute a qualquer momento:

```bash
~/AI/scripts/gpu-check.sh
```

O script mostra: GPU, VRAM, driver, CUDA, temperatura, consumo, utilização,
versão Python, PyTorch, Ollama. Não altera nenhuma configuração.

---

## Etapa 14 — Relatório final

Execute e documente os resultados:

```bash
# Diagnóstico completo
~/AI/scripts/gpu-check.sh

# Confirmação PyTorch
source ~/ai-env/bin/activate
python -c "
import torch
x = torch.randn(5000, 5000, device='cuda')
y = torch.matmul(x, x)
torch.cuda.synchronize()
print('CUDA TESTE: OK')
print('GPU:', torch.cuda.get_device_name(0))
"

# Status Ollama
ollama --version
systemctl status ollama --no-pager

# Docker
docker --version
```

### Template de relatório

```
=== RELATÓRIO FINAL — MÁQUINA IA LOCAL ===
Data: _______________

HARDWARE
  CPU       : AMD Ryzen 7 5700X
  RAM       : 32 GB DDR4
  GPU       : NVIDIA GeForce RTX 3060
  VRAM      : 12288 MiB
  SSD       : ___ GB NVMe
  OS        : Windows 11 Build ___

NVIDIA
  Driver    : ___
  CUDA sup. : ___
  Temp idle : ___ °C
  Estado    : OK / AVISO

WSL
  Versão    : ___
  Distro    : Ubuntu ___
  Kernel    : ___
  GPU WSL   : detectada / NÃO detectada

PYTHON
  Versão    : ___
  venv      : ~/ai-env — ativo

PYTORCH
  Versão    : ___
  CUDA      : True / False
  GPU       : ___
  VRAM      : ___ GB
  Teste     : APROVADO / REPROVADO

OLLAMA
  Versão    : ___
  Serviço   : ativo / inativo
  GPU       : utilizada / CPU apenas
  Qwen3:8b  : APROVADO / REPROVADO

DOCKER
  Versão    : ___
  Estado    : funcionando / não instalado

RESULTADO FINAL
  [ ] APROVADA PARA IA LOCAL
  [ ] APROVADA COM RESSALVAS — ___
  [ ] NÃO APROVADA — ___
```

---

## Regras de segurança

- Não fazer overclock, undervolt ou alterar limites de potência
- Não alterar BIOS
- Não instalar drivers NVIDIA alternativos se o atual funcionar
- Não instalar múltiplas versões conflitantes do CUDA Toolkit
- Não instalar pacotes Python globalmente — usar sempre o venv
- Não baixar modelos grandes (>13B) sem verificar espaço disponível
- Não ocupar mais de 80% do SSD com modelos
- Não alterar configurações permanentes sem documentar o motivo

---

## Referências

- PyTorch: https://pytorch.org/get-started/locally/
- Ollama: https://ollama.com
- WSL: https://learn.microsoft.com/windows/wsl/
- Docker Desktop WSL: https://docs.docker.com/desktop/wsl/
- NVIDIA CUDA WSL: https://docs.nvidia.com/cuda/wsl-user-guide/
