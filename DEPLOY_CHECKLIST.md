# FlowCore — Deploy Checklist

Este documento lista todos os passos para validar uma instalação do FlowCore em um dispositivo Android com Termux limpo.

---

## Pre-requisitos

| Item | Mínimo | Verificação |
|------|--------|-------------|
| Android | 12+ | Configurações > Sobre o telefone |
| RAM livre | 512 MB | No comando livre |
| Espaço em disco | 100 MB | `df -m /` |
| Internet | Ativa | `ping -c 1 github.com` |
| Termux | 0.118+ | F-Droid ou Termux:Boot |

---

## Passo 1: Preparar o Termux

```bash
termux-setup-storage
pkg update && pkg upgrade -y
pkg install python git openssl -y
```

**Validação:**
```bash
python3 --version       # Deve mostrar >= 3.11
git --version           # Deve funcionar
which openssl           # Deve mostrar caminho
```

---

## Passo 2: Clonar o Repositório

```bash
cd ~
git clone https://github.com/prdariomarques-ship-it/FlowCore.git
cd FlowCore
```

**Validação:**
```bash
ls -la                          # Deve mostrar install.sh, flowcore.py, etc.
git log --oneline               # Deve mostrar pelo menos 2 commits
git tag                         # Deve mostrar v1.0.0
```

---

## Passo 3: Executar a Instalação

```bash
bash install.sh
```

**O que o install.sh verifica automaticamente:**

| Check | Ação |
|-------|------|
| Internet | Ping para github.com e pypi.org |
| Disco | Mínimo 100 MB livres |
| Python | Versão >= 3.11 |
| Dependências | Instala via pip |
| Config | Valida config/default.yml |
| Segurança | Confirma API em localhost |
| Módulos | Importa yaml, fastapi, loguru, aiosqlite |

**Validação pós-instalação:**
```bash
cat logs/install.log        # Sem [ERROR]
ls -la data/                # Deve existir
ls -la backups/             # Deve existir
```

---

## Passo 4: Self-Test

```bash
python3 flowcore.py selftest
```

**Resultado esperado:** `ALL TESTS PASSED: 35/35`

| Grupo | Checks |
|-------|--------|
| Imports | 8 módulos |
| Config | 1 check |
| Database | 2 checks |
| Executor | 1 check |
| Scheduler | 1 check |
| Agents | 2 checks |
| API | 2 checks |
| CLI | 1 check |
| Directories | 10 checks |
| Files | 6 checks |
| Logging | 1 check |

---

## Passo 5: Validar a API

```bash
python3 flowcore.py serve &
sleep 3
curl http://127.0.0.1:8080/api/health
kill %1
```

**Resposta esperada:**
```json
{"status": "ok", "version": "1.0.0", "uptime_seconds": 3.0}
```

**Verificação de segurança:**
```bash
curl http://0.0.0.0:8080/api/health    # Deve FALHAR (localhost only)
```

---

## Passo 6: Validar o Daemon

```bash
python3 daemon.py start
sleep 2
python3 daemon.py status
python3 daemon.py stop
```

**Validação:**
```bash
python3 daemon.py status    # Deve mostrar "stopped"
```

---

## Passo 7: Auditoria de Segurança

```bash
python3 scripts/audit.py
bash validate_android.sh
```

**Resultado esperado:**
- Audit: `30 passed, 0 failed, 0 warnings`
- Validate: todos os checks com status OK

---

## Passo 8: Verificar Diretórios

```bash
find . -maxdepth 2 -type f -not -path "./.git/*" -not -path "./logs/*" -not -path "./data/*" -not -path "./backups/*" | sort
```

**Arquivos obrigatórios:**

| Arquivo | Obrigatório |
|---------|-------------|
| `flowcore.py` | Sim |
| `daemon.py` | Sim |
| `install.sh` | Sim |
| `validate_android.sh` | Sim |
| `doctor.sh` | Sim |
| `optimize.sh` | Sim |
| `benchmark.sh` | Sim |
| `update.sh` | Sim |
| `repair.sh` | Sim |
| `uninstall.sh` | Sim |
| `requirements.txt` | Sim |
| `README.md` | Sim |
| `LICENSE` | Sim |
| `VERSION` | Sim |
| `CHANGELOG.md` | Sim |
| `ARCHITECTURE.md` | Sim |
| `ROADMAP.md` | Sim |
| `CONTRIBUTING.md` | Sim |
| `SECURITY.md` | Sim |
| `CODEOWNERS` | Sim |
| `config/default.yml` | Sim |
| `config/loader.py` | Sim |

---

## Passo 9: Teste de Recursos

```bash
# CPU usage (deve ser baixo)
top -b -n 1 | grep python

# RAM usage (deve ser < 200MB)
free -m | grep Mem

# Battery impact (deve ser baixo)
termux-battery-status
```

---

## Resumo Final

| Passo | Comandos | Resultado Esperado |
|-------|----------|-------------------|
| 1. Preparar | `pkg install python git openssl` | Python 3.11+ |
| 2. Clonar | `git clone ...` | 32+ arquivos |
| 3. Instalar | `bash install.sh` | Installation Complete |
| 4. Self-test | `python3 flowcore.py selftest` | 35/35 PASSED |
| 5. API | `curl 127.0.0.1:8080/api/health` | `{"status": "ok"}` |
| 6. Daemon | `python3 daemon.py start/stop` | Status OK |
| 7. Segurança | `python3 scripts/audit.py` | 30/30 PASS |
| 8. Diretórios | `find . -maxdepth 2` | Todos presentes |
| 9. Recursos | `top / free / battery` | Baixo impacto |

**Se todos os 9 passos passaram: FlowCore está pronto para produção.**
