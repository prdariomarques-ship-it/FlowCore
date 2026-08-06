# FlowCore — Plano de Sprints

**Versão:** 2.0
**Data:** 2026-08-02
**Baseado em:** ADR-007, android-runtime-spec.md, feedback arquitetural Sprint 8

---

## Premissa permanente

O ambiente de produção do FlowCore é um smartphone Android com Termux.
Todo componente deve responder à FLOWCORE DESIGN RULE antes de ser aceito.
Ver: `docs/runtime/android-runtime-spec.md`

---

## As duas linhas do tempo

### Linha 1 — Produto atual (realidade)

```
CLI
 ↓
Business Logic (flowcore.py)
 ↓
Storage (DocumentRepository / MemoryRepository)
 ↓
SQLite / JSON
```

Esta linha existe e funciona. Não pode regredir.

### Linha 2 — Arquitetura futura (visão)

```
Presentation (CLI / MCP / API)
 ↓
Intent Engine → Reasoning Engine (Passport) → Execution Engine
 ↓
Runtime Kernel
 ↓
Android Runtime → Termux Runtime → Linux Runtime
 ↓
Capability Registry → Capability Adapters
 ↓
Android APIs / Termux API / Linux APIs
 ↓
Hardware
```

Esta linha está sendo construída Sprint a Sprint.
O erro seria fingir que ela já existe.

---

## Regra de qualidade (todos os Sprints)

1. Nenhum commit sem testes passando
2. Zero regressões nos comandos existentes (`selftest`, `health`, `doctor`)
3. Todo adapter retorna `CapabilityResult` — nunca levanta exceções
4. Todo `run()` tem timeout explícito
5. Nenhum `os.system()`, `subprocess.run()` ou `shell=True`
6. O LLM nunca recebe comandos de shell — apenas nomes de capacidades
7. Toda capacidade define Preferred + fallback chain
8. Documentação ADR para cada decisão arquitetural

---

## Sprint 7 — Consolidação Arquitetural ✅ CONCLUÍDA

**Objetivo:** Eliminar dívida técnica e estabelecer fundações limpas.

**Entregáveis concluídos:**
- [x] Camada `storage/` com `DocumentRepository` e `MemoryRepository`
- [x] Eliminação do padrão DB duplicado (8+ ocorrências em flowcore.py)
- [x] Bug fix: `load_config(self.root)` → `load_config()` em runtime/core.py
- [x] Bug fix: `default.yml` → `default.json` em scripts/audit.py
- [x] flowcore.py reduzido via delegation para repositories
- [x] ADR-007 — Revisão Arquitetural Completa
- [x] SPRINT_PLAN.md (versão 1.0)

---

## Sprint 8 — Runtime Kernel ✅ CONCLUÍDA

**Objetivo:** Transformar o Termux de um "provider simples" em um runtime vivo,
com boot sequence real, saúde verificada e Passport emitido.

**Entregáveis concluídos:**

```
runtime/
├── shell.py        ← gateway subprocess controlado (Popen, sem shell=True)
├── discovery.py    ← RuntimeDiscovery: plataforma, env, 19 ferramentas, rede
└── kernel.py       ← RuntimeKernel (boot 5 etapas) + RuntimePassport

capability/
├── adapters/
│   ├── base.py     ← CapabilityAdapter ABC + CapabilityResult
│   ├── android.py  ← AndroidAdapter  (priority 100) — termux-* commands
│   ├── termux.py   ← TermuxAdapter   (priority 80)  — Linux no Android
│   └── linux.py    ← LinuxAdapter    (priority 50)  — desktop/server/CI
├── registry.py     ← CapabilityRegistry — mapeia nomes → adapters
└── resolver.py     ← ProviderResolver  — fallback automático

doctor/
└── service.py      ← DoctorService — 27 checks (Android, tools, rede, AI bridges)

installer/
└── setup.py        ← FlowCoreInstaller — setup idempotente em 10 etapas
```

**CLI adicionada:**
- `python3 flowcore.py boot` — executa boot sequence, emite Passport
- `python3 flowcore.py install` — configura ambiente completo

**Resultado verificado neste ambiente (Linux/CI):**
```
Platform: linux | Capabilities: runPython, runGit, httpRequest, internetAccess, runDocker
Doctor: 8/27 checks passed (4 warnings, 0 failures) — healthy=True
```

No Android com Termux:API, o resultado seria:
```
Platform: termux | Capabilities: + getBattery, getClipboard, sendNotification, getAndroidInfo
```

---

## Sprint 9 — Android Runtime (PRÓXIMA)

**Objetivo:** Aprofundar o AndroidAdapter com o conjunto completo de APIs Android:
Bluetooth, câmera, intents, WakeLock, modo vibração, sensores.

**Por que agora:** O AndroidAdapter atual cobre apenas as APIs básicas do Termux:API.
O celular oferece muito mais — e o FlowCore precisa de acesso a esses recursos
para sobreviver em background, gerir bateria e se comunicar com outros apps.

**FLOWCORE DESIGN RULE aplicada:**
- Todas as capacidades desta Sprint vivem no Android
- Fallback Termux obrigatório para cada nova capacidade
- Consumo de bateria documentado para cada operação
- Sobrevivência ao kill do app verificada

**Entregáveis planejados:**

```
capability/adapters/android.py  ← ampliar com:
  get_bluetooth_state()         — termux-bluetooth-get-adapters
  get_sensors()                 — termux-sensor
  get_location()                — termux-location (GPS)
  get_wifi_scan()               — termux-wifi-scaninfo
  vibrate()                     — termux-vibrate
  play_sound()                  — termux-media-player
  open_url()                    — termux-open-url (intent)
  torch()                       — termux-torch
  take_photo()                  — termux-camera-photo

runtime/wakelock.py             ← WakeLock para manter processo vivo
runtime/boot_receiver.py        ← re-execução via Termux:Boot após reboot
```

**Testes mínimos:** 15 testes — cada nova capacidade com mock do termux-* command.

**Critério de aceitação:**
- `python3 flowcore.py boot` no Android lista as novas capacidades
- Doctor verifica Termux:Boot instalado e configurado

---

## Sprint 10 — Termux Runtime

**Objetivo:** Aprofundar o TermuxAdapter com serviços de longa duração, cron,
SQLite nativo, rsync e gestão de processos em background.

**Por que agora:** O TermuxAdapter atual é transacional (executa e retorna).
Para o FlowCore viver no celular, ele precisa de processos persistentes:
sync periódico, daemon leve, jobs agendados.

**FLOWCORE DESIGN RULE aplicada:**
- Processos em background: podem ser mortos pelo Android — checkpoint obrigatório
- Jobs cron: verificar se `crond` sobrevive ao sleep do aparelho
- SQLite: WAL mode para evitar corrupção por kill abrupto

**Entregáveis planejados:**

```
capability/adapters/termux.py  ← ampliar com:
  run_sqlite(db, query)         — sqlite3 nativo via subprocess
  rsync(src, dst, *, opts)      — rsync para backup/sync
  start_cron(script, schedule)  — termux-job-scheduler ou crond
  run_background(script)        — processo em background com PID tracking

runtime/daemon.py              ← daemon leve (substitui daemon.py atual)
runtime/checkpoint.py          ← persiste estado de tasks em disco
runtime/job_scheduler.py       ← agenda tasks recorrentes
```

**Testes mínimos:** 15 testes — daemon lifecycle, cron scheduling, SQLite queries.

**Critério de aceitação:**
- `python3 flowcore.py boot` detecta crond / termux-job-scheduler
- Doctor verifica estado do daemon e jobs agendados

---

## Sprint 11 — Capability Registry v2 + Contratos

**Objetivo:** Formalizar os contratos de capacidade com tipos, versionamento
e o arquivo `flowcore.capabilities.json`.

**Por que depois:** O Registry atual é funcional mas sem contratos formais.
Com Android Runtime e Termux Runtime completos (Sprints 9-10),
o Registry tem substância concreta para representar.

**Entregáveis planejados:**

```
capability/contracts.py  ← Capability, Provider, Resolution (tipos formalizados)
capability/registry.py   ← versão 2 com suporte a contratos e versionamento

flowcore.capabilities.json  ← gerado em boot, lista capacidades e seus providers:
{
  "schema_version": "1.0",
  "capabilities": {
    "getBattery":    { "provider": "android",  "fallback": "termux" },
    "getClipboard":  { "provider": "android",  "fallback": null },
    "runPython":     { "provider": "termux",   "fallback": "linux" },
    "httpRequest":   { "provider": "termux",   "fallback": "linux" }
  }
}
```

**Testes mínimos:** 20 testes — registro, resolução, fallback chain, versionamento.

---

## Sprint 12 — Passport

**Objetivo:** Todo agente recebe um Passport antes de executar.
Sem Passport, sem execução.

**Por que depois do Registry:** O Passport encapsula as capacidades disponíveis
(do Registry), o estado da plataforma (do Kernel) e a identidade do agente.
Precisa dos três anteriores para ser completo.

**Entregáveis planejados:**

```
passport/
├── __init__.py
├── generator.py   ← PassportGenerator
├── validator.py   ← PassportValidator
└── schema.py      ← Passport, AgentIdentity, RuntimeInfo (dataclasses)
```

**Conteúdo do Passport:**
```json
{
  "agent": { "name": "health_agent", "version": "0.1.0" },
  "platform": "termux",
  "capabilities": ["getBattery", "runPython", "httpRequest"],
  "permissions": ["getBattery", "readFile"],
  "health": { "status": "ok" },
  "issued_at": "<iso8601>",
  "expires_at": "<iso8601>",
  "hash": "<sha256>"
}
```

**Testes mínimos:** 15 testes — emissão, validação, expiração, revogação.

---

## Sprint 13 — MCP

**Objetivo:** FlowCore como MCP Server, expondo capacidades para agentes externos.

**Entregáveis planejados:**

```
mcp/
├── __init__.py
├── server.py   ← FlowCore como MCP Server
└── tools.py    ← Tools: remember, recall, search, ask, getBattery, runPython, ...
```

**Resultado:** Claude, GPT e outros agentes externos usam as capacidades do FlowCore
sem conhecer a implementação interna.

---

## Visão ao final das Sprints

```
Presentation (CLI / MCP / API)
        ↓
    Intent Engine
        ↓
    Reasoning Engine       ← agentes com Passport
        ↓
    Execution Engine       ← task queue, retry, checkpoint
        ↓
    Runtime Kernel         ← boot, doctor, runtime.json
        ↓
    Android Runtime        ← Battery, Bluetooth, Camera, Sensors, Intents
        ↓
    Termux Runtime         ← Python, Git, SSH, SQLite, Cron, Daemon
        ↓
    Capability Registry    ← contratos formais, resolução automática
        ↓
    Linux / Docker / Oracle  ← extensões para cloud e desktop
        ↓
    MCP Layer              ← exposição para agentes externos
```

| Plataforma   | Adapter        | Sprint   | Status     |
|---|---|---|---|
| Android      | AndroidAdapter | 8 (base) + 9 | Em progresso |
| Termux       | TermuxAdapter  | 8 (base) + 10 | Em progresso |
| Linux/macOS  | LinuxAdapter   | 8        | Concluído  |
| Docker       | —              | pós-13   | Planejado  |
| Oracle Cloud | —              | pós-13   | Planejado  |
| MCP          | —              | 13       | Planejado  |
