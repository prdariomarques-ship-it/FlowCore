# FlowCore Android Runtime Specification

**Versão:** 1.0
**Data:** 2026-08-02
**Status:** Canonical — todos os agentes seguem este documento

---

## Premissa central

O ambiente de produção do FlowCore é um smartphone Android com Termux.

Não é um servidor Linux.
Não é um container Docker.
Não é um Mac.

Tudo o que for construído deve funcionar primeiro no celular.
Desktop e Cloud são extensões, não o alvo.

---

## Stack oficial

```
FlowCore Brain
      ↓
Intent Engine
      ↓
Reasoning Engine         ← agentes com Passport
      ↓
Execution Engine         ← task queue, retry, timeout
      ↓
Runtime Manager          ← lifecycle, health, boot sequence
      ↓
Runtime Kernel           ← descobre, valida, emite Passport
      ↓
Android Runtime          ← APIs nativas via Termux:API
      ↓
Termux Runtime           ← Linux no Android (Python, Git, SSH)
      ↓
Capability Adapters      ← única camada que conhece comandos reais
      ↓
Android APIs / Linux APIs / Termux API
      ↓
Hardware
```

---

## Camadas e responsabilidades

### Runtime Kernel
- Responsável pelo boot sequence completo
- Produz `flowcore.runtime.json`
- Emite o Runtime Passport
- Delega ao Doctor para validação de saúde

### Android Runtime (`capability/adapters/android.py`)
Interface para APIs Android via Termux:API.

| Capacidade | Comando real | Permissão necessária |
|---|---|---|
| `getBattery` | `termux-battery-status` | — |
| `getClipboard` | `termux-clipboard-get` | — |
| `setClipboard` | `termux-clipboard-set` | — |
| `sendNotification` | `termux-notification` | NOTIFICATIONS |
| `getNetworkInfo` | `termux-wifi-connectioninfo` | ACCESS_WIFI_STATE |
| `getAndroidInfo` | `getprop` | — |

**Regra:** O Reasoning Engine nunca vê `termux-battery-status`.
Ele vê apenas `getBattery()`.

### Termux Runtime (`capability/adapters/termux.py`)
Interface para o ambiente Linux dentro do Android.

| Capacidade | Implementação |
|---|---|
| `runPython` | `python3 <script>` |
| `runGit` | `git <args>` |
| `runSSH` | `ssh [-i key] host <cmd>` |
| `installPackage` | `pkg install` → fallback `pip` |
| `httpRequest` | `curl` → fallback `urllib` |
| `readFile` / `writeFile` / `listDirectory` | `pathlib.Path` |
| `getBattery` | `/sys/class/power_supply/` (fallback sem Termux:API) |

### Linux Runtime (`capability/adapters/linux.py`)
Fallback para desktop, CI, Oracle Cloud, WSL.
Prioridade mais baixa (50). Nunca tem preferência sobre Android ou Termux.

---

## Regra de resolução de providers

```
Android (priority 100)
    ↓ se indisponível ou falhou
Termux (priority 80)
    ↓ se indisponível ou falhou
Linux  (priority 50)
    ↓ se indisponível ou falhou
CapabilityResult.fail("No adapter available")
```

O `ProviderResolver` aplica esta cadeia automaticamente.
O agente nunca escolhe o adapter — ele apenas solicita a capacidade.

---

## Boot sequence

```
BOOT
  ↓
[1] Runtime Discovery
    Detecta: platform_type, Python, env vars, 19 tools, network
  ↓
[2] Health Validation (Doctor — non-blocking)
    27 checks: Android, Termux, tools, permissões, rede, AI bridges
  ↓
[3] Capabilities
    Deriva lista de capacidades a partir das ferramentas descobertas
  ↓
[4] Persist
    Escreve ~/.flowcore/flowcore.runtime.json
  ↓
[5] Passport
    Emite RuntimePassport (imutável)
  ↓
READY
```

---

## flowcore.runtime.json — campos obrigatórios

```json
{
  "schema_version": "1.0",
  "generated_at": "<iso8601>",
  "platform_type": "termux | android | linux | macos | docker | windows",
  "python_version": "3.x.x",
  "architecture": "aarch64 | x86_64",
  "env": {
    "PREFIX": "/data/data/com.termux/files/usr",
    "HOME": "/data/data/com.termux/files/home",
    "TMPDIR": "...",
    "PATH": "..."
  },
  "android": {
    "detected": true,
    "version": "14",
    "sdk": "34",
    "device_model": "...",
    "cpu_abi": "arm64-v8a"
  },
  "termux": {
    "detected": true,
    "prefix": "...",
    "api_available": true,
    "pkg_available": true,
    "storage_available": true
  },
  "tools": {
    "python3": { "available": true, "version": "3.11.x", "path": "..." },
    "git":     { "available": true, "version": "2.x", "path": "..." }
  },
  "network": {
    "internet": true,
    "dns": true,
    "hostname": "...",
    "oracle_reachable": false,
    "docker_reachable": false,
    "mcp_reachable": false
  },
  "capabilities": ["runPython", "runGit", "httpRequest", "getBattery", "getClipboard"],
  "hash": "<sha256[:16]>"
}
```

---

## FLOWCORE DESIGN RULE

**Todo componente novo deve responder às seguintes perguntas antes de ser aceito:**

| Pergunta | Por quê importa |
|---|---|
| Como funcionará dentro do Android? | Android é o ambiente de produção |
| Como funcionará dentro do Termux? | Termux é o runtime de produção |
| Quais permissões Android serão necessárias? | Permissão negada = funcionalidade morta |
| Quais APIs Android serão utilizadas? | Define qual adapter implementa |
| Existe fallback? | Degradação graceful é obrigatória |
| Qual o consumo esperado de bateria? | Celular tem bateria limitada |
| Pode sobreviver ao encerramento do app? | Android mata processos em background |
| Pode sobreviver ao reboot do aparelho? | Estado persistente deve ser explícito |

**Componentes que não respondem a estas perguntas não são aceitos.**

Esta regra se aplica a:
- Novos adapters
- Novos serviços
- Novas capacidades
- Novas dependências externas
- Qualquer código que acesse I/O, rede, ou sistema de arquivos

---

## Permissões Android requeridas

| Permissão | Capacidade | Adapter |
|---|---|---|
| `RECEIVE_BOOT_COMPLETED` | Reinício automático | Runtime Kernel |
| `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` | Background contínuo | Runtime Manager |
| `POST_NOTIFICATIONS` | `sendNotification` | AndroidAdapter |
| `ACCESS_WIFI_STATE` | `getNetworkInfo` | AndroidAdapter |
| `READ_EXTERNAL_STORAGE` | `readFile` (SD card) | AndroidAdapter |
| `WRITE_EXTERNAL_STORAGE` | `writeFile` (SD card) | AndroidAdapter |

---

## Considerações de bateria

| Operação | Impacto | Estratégia |
|---|---|---|
| Boot sequence | Médio (uma vez) | Executar apenas no primeiro boot ou mudança de config |
| Doctor (27 checks) | Médio | Cachear resultado por 15 minutos |
| RuntimeDiscovery | Baixo | Re-executar somente quando `PREFIX` ou `PATH` mudar |
| HTTP requests | Alto (rádio) | Batching, timeout curto, fallback local |
| SSH | Alto | Pool de conexões, keepalive controlado |
| Subprocessos | Variável | `timeout` obrigatório em toda chamada `run()` |

---

## Sobrevivência ao encerramento do app

O Android pode matar o processo Termux a qualquer momento.

**Estratégias implementadas:**

1. `flowcore.runtime.json` — estado persistido após cada boot
2. `memories.json` — memórias persistidas em arquivo, não em RAM
3. `flowcore.db` — SQLite (ACID, sobrevive a crashes)
4. Doctor não bloqueia boot — warnings não impedem execução
5. Todos os adapters retornam `CapabilityResult` (nunca levantam exceções)

**Estratégias pendentes (próximas Sprints):**

- Termux:Boot para re-execução automática após reboot
- Modo daemon leve para tarefas em background
- Checkpoint de tasks pendentes em disco

---

## Dois estados do FlowCore

### Estado atual (Linha 1)

```
CLI
 ↓
Business Logic (flowcore.py)
 ↓
Storage Layer (DocumentRepository / MemoryRepository)
 ↓
SQLite / JSON
```

Produto funcional. Estável. Base para a Linha 2.

### Visão futura (Linha 2)

```
Presentation (CLI / MCP / API)
 ↓
Intent Engine
 ↓
Reasoning Engine  ← agentes com Passport
 ↓
Context Engine
 ↓
Execution Engine
 ↓
Runtime Manager
 ↓
Bridge Layer (Android | Termux | Linux | Docker | Oracle)
 ↓
Operating System
```

**O erro seria fingir que a Linha 2 já existe.**
**O objetivo das próximas Sprints é construir a ponte entre elas.**

---

## Agentes e suas responsabilidades

| Agente | Responsabilidade |
|---|---|
| Jules | Arquitetura — desenha contratos, camadas, decisões |
| Qwen | Implementação — escreve o código seguindo os contratos |
| GLM | Auditoria — valida segurança, compliance, bugs |
| Claude Code | Integração — refatoração, consistência, boot sequence, testes |

**Todos os agentes leem este documento antes de qualquer Sprint.**
