# FlowCore — Plano das Próximas 5 Sprints

**Versão:** 1.0  
**Data:** 2026-08-02  
**Baseado em:** ADR-007 (Revisão Arquitetural)

---

## Premissas

1. O LLM nunca executa comandos Linux diretamente — apenas solicita capacidades.
2. Android é o SO principal; Termux é um runtime Linux dentro do Android.
3. Retrocompatibilidade de contratos e CLI deve ser preservada.
4. Cada Sprint deve ter testes aprovados antes de avançar.
5. Simples e modular supera complexo e acoplado.

---

## Sprint 7 — Consolidação Arquitetural (ATUAL)

**Objetivo:** Eliminar dívida técnica e estabelecer fundações limpas.

**Entregáveis:**

- [x] Camada `storage/` com `DocumentRepository` e `MemoryRepository`
- [x] Eliminação do padrão DB duplicado (8+ ocorrências em flowcore.py)
- [x] Bug fix: `load_config(self.root)` → `load_config()` em runtime/core.py
- [x] Bug fix: `default.yml` → `default.json` em scripts/audit.py
- [x] flowcore.py reduzido via delegation para repositories
- [x] ADR-007 — Revisão Arquitetural Completa
- [x] SPRINT_PLAN.md (este documento)

**Critérios de aceitação:**
- `python3 flowcore.py selftest` → todos PASS
- `python3 scripts/audit.py` → zero FAIL
- Sem regressões nos comandos existentes

**Responsáveis:** Claude Code

---

## Sprint 8 — Context Engine

**Objetivo:** Implementar o Context Engine descrito na visão (Sprint 1 do handoff
que nunca foi construído).

**Por que agora:** O Context Engine é a fundação sobre a qual o Passport e o
Capability Registry dependem. Sem ele, os Sprints 9-11 não têm base.

**Entregáveis:**

```
context/
├── __init__.py
├── engine.py           # ContextEngine — orquestrador
├── workspace_scanner.py  # Detecta arquivos, Git, linguagens
├── project_classifier.py # Classifica tipo de projeto
├── artifact_detector.py  # Detecta artefatos (configs, schemas, docs)
└── serializer.py       # ContextSerializer — produz flowcore.context.json
```

**Contrato de saída (`flowcore.context.json`):**
```json
{
  "schema_version": "1.0",
  "timestamp": "<iso8601>",
  "workspace": {
    "root": "/path/to/project",
    "type": "python_cli",
    "language": "python",
    "vcs": "git",
    "branch": "main"
  },
  "artifacts": {
    "config_files": ["config/default.json"],
    "entry_points": ["flowcore.py"],
    "test_files": []
  },
  "hash": "<sha256 do conteúdo>"
}
```

**Testes mínimos:** 15 testes cobrindo scan, classificação, detecção e serialização.

**Responsáveis:** Jules (arquitetura), Qwen (implementação), GLM (auditoria)

---

## Sprint 9 — Bridge Layer + Capability Registry

**Objetivo:** Implementar a camada de Bridge que separa o LLM do sistema operacional,
e o Capability Registry com resolução por provider.

**A regra mais importante do projeto se aplica aqui:**  
*O LLM (agente) nunca conhece `termux-battery-status`, `ip addr`, `pkg`, `pip`, `ls`.*  
*O agente solicita apenas capacidades: `getBattery()`, `getNetworkInfo()`.*

**Entregáveis:**

```
bridges/
├── __init__.py
├── base.py             # PlatformBridge (Protocol/ABC)
├── android_bridge.py   # BatteryManager, WiFi, Bluetooth, Camera, Storage, Intents
├── termux_bridge.py    # Python, Git, SSH, SQLite, FileSystem, Shell, Cron
├── linux_bridge.py     # Versão desktop/server (Ubuntu, macOS, Oracle)
└── shell_bridge.py     # Fallback genérico via subprocess controlado

capability/
├── __init__.py
├── registry.py         # CapabilityRegistry
├── resolver.py         # ProviderResolver — Preferred → Fallback → Fallback
└── contracts.py        # Tipos: Capability, Provider, Resolution
```

**Regra de resolução (exemplo):**
```python
BATTERY = Capability(
    name="getBattery",
    preferred=AndroidBridge,
    fallbacks=[TermuxBridge, ShellBridge],
)
```

**Runtime Contract (`flowcore.runtime.json`):**
```json
{
  "schema_version": "1.0",
  "platform": "android",
  "runtime": "termux",
  "bridges_available": ["android", "termux"],
  "capabilities": ["getBattery", "getNetworkInfo", "readFile", "runPython"]
}
```

**Testes mínimos:** 20 testes cobrindo registro, resolução, fallbacks e bridges.

**Responsáveis:** Jules (arquitetura/contracts), Qwen (implementação), GLM (auditoria)

---

## Sprint 10 — FlowCore Passport

**Objetivo:** Todo agente recebe automaticamente um Passport completo antes de executar.
Sem Passport, sem execução.

**O Passport é o objeto que materializa a frase:**  
*"Nenhum agente trabalha sem Passport."*

**Entregáveis:**

```
passport/
├── __init__.py
├── generator.py        # PassportGenerator
├── validator.py        # PassportValidator
└── schema.py           # Tipos: Passport, AgentIdentity, RuntimeInfo
```

**Conteúdo do Passport:**
```json
{
  "schema_version": "1.0",
  "agent": {
    "name": "health_agent",
    "version": "0.1.0"
  },
  "workspace": { ... },   // do Context Contract
  "runtime": { ... },     // do Runtime Contract
  "capabilities": [ ... ], // do Capability Contract
  "permissions": ["getBattery", "readFile"],
  "health": { "status": "ok" },
  "issued_at": "<iso8601>",
  "expires_at": "<iso8601>",
  "hash": "<sha256>"
}
```

**Integração com AgentRegistry:**
- `AgentRegistry.run(name, context)` emite Passport antes de chamar `agent.run()`
- Agente recebe o Passport via `context["passport"]`
- Passport pode ser revogado (permissions=[]) para agentes sem autorização

**Capability Contract (`flowcore.capabilities.json`):**
```json
{
  "schema_version": "1.0",
  "capabilities": {
    "getBattery": { "bridge": "android", "fallback": "termux" },
    "readFile": { "bridge": "termux", "fallback": "linux" }
  }
}
```

**Testes mínimos:** 15 testes cobrindo emissão, validação, expiração, revogação.

**Responsáveis:** Jules (arquitetura), Qwen (implementação), GLM (auditoria/segurança)

---

## Sprint 11 — Multi-Runtime + MCP

**Objetivo:** Expandir o FlowCore para além do Android/Termux, preparando para
Oracle Cloud, Docker, Windows e integração MCP.

**Entregáveis:**

```
bridges/
├── docker_bridge.py    # Container runtime
├── oracle_bridge.py    # Oracle Cloud (OCI SDK)
└── windows_bridge.py   # Windows (PowerShell, WinAPI)

mcp/
├── __init__.py
├── server.py           # FlowCore como MCP Server
└── tools.py            # Tools expostos: remember, search, ask, capabilities
```

**Regras de expansão:**
- Cada novo Bridge implementa `PlatformBridge` (Protocol do Sprint 9)
- Capability Registry descobre bridges disponíveis por plataforma em boot
- Sem modificar contratos existentes (retrocompatibilidade total)

**MCP Integration:**
- FlowCore expõe `remember`, `recall`, `search`, `ask`, `getBattery`, etc. como MCP Tools
- Permite que agentes externos (Claude, GPT, etc.) usem as capacidades do FlowCore
  sem conhecer a implementação

**Docker:**
```dockerfile
FROM python:3.11-slim
COPY . /flowcore
WORKDIR /flowcore
RUN pip install -r requirements-core.txt
CMD ["python3", "flowcore.py", "serve"]
```

**Testes mínimos:** 10 testes por bridge + 10 testes MCP.

**Responsáveis:** Jules (arquitetura), Qwen (implementação), GLM (auditoria), Claude Code (MCP)

---

## Visão ao Final dos 5 Sprints

```
Presentation (CLI / MCP / API)
        ↓
    Intent Layer  (parse → intenção)
        ↓
    Reasoning Layer  (agentes com Passport)
        ↓
    Context Engine  (workspace, projeto, artefatos)
        ↓
    Execution Engine  (Task, retry, timeout)
        ↓
    Runtime Manager  (lifecycle, health)
        ↓
    Bridge Layer  (Android | Termux | Linux | Docker | Oracle | Windows)
        ↓
    Operating System
```

**Plataformas suportadas após Sprint 11:**

| Plataforma     | Bridge         | Status        |
|----------------|----------------|---------------|
| Android        | AndroidBridge  | Sprint 9      |
| Termux         | TermuxBridge   | Sprint 9      |
| Linux/macOS    | LinuxBridge    | Sprint 9      |
| Docker         | DockerBridge   | Sprint 11     |
| Oracle Cloud   | OracleBridge   | Sprint 11     |
| Windows        | WindowsBridge  | Sprint 11     |
| MCP (qualquer) | FlowCore Tools | Sprint 11     |

---

## Regras de Qualidade (todos os Sprints)

1. Nenhum commit sem testes passando
2. Zero regressões na selftest existente
3. Contratos são versionados e imutáveis após publicação
4. Toda capacidade define Preferred + 2 Fallbacks
5. O LLM nunca recebe comandos de shell — apenas nomes de capacidades
6. Passport obrigatório para execução de agentes
7. Documentação ADR para cada decisão arquitetural
