# ADR-007 — Revisão Arquitetural Completa (Sprint 7)

**Data:** 2026-08-02  
**Status:** Aceito  
**Autor:** Claude Code (Lead Systems Engineer)

---

## Contexto

Esta ADR documenta a revisão arquitetural completa do FlowCore realizada em Sprint 7,
cobrindo todos os módulos implementados até Sprint 6. Serve como base para o plano
das próximas cinco Sprints.

---

## 1. Estado Real vs. Estado Descrito no Handoff

O handoff descreve Sprints 1-3 como concluídos (Context Engine, Platform Evolution,
Runtime Foundation). **Esses componentes não existem no repositório.**

O código real evoluiu por um caminho diferente, implementando funcionalidades orientadas
ao usuário final:

| Sprint (Handoff) | Descrição             | Implementado? |
|------------------|-----------------------|---------------|
| Sprint 1         | Context Engine        | ✗ Não         |
| Sprint 2         | Platform Evolution    | ✗ Não         |
| Sprint 3         | Runtime Foundation    | ✗ Parcial     |
| Sprint 5 (git)   | Daily + Search        | ✓ Sim         |
| Sprint 6 (git)   | Obsidian Integration  | ✓ Sim         |

Componentes da visão que não existem no código:
- `WorkspaceScanner`, `ProjectClassifier`, `ArtifactDetector`, `ContextEngine`
- `flowcore.context.json`, `flowcore.runtime.json`, `flowcore.capabilities.json`
- `AndroidBridge`, `TermuxBridge`, `LinuxBridge`
- `CapabilityRegistry`, Provider Resolution
- `FlowCore Passport`
- `RuntimeManager`, `RuntimeBootloader`, `RuntimeHealthChecker`, `RuntimePassport`

---

## 2. Problemas Arquiteturais Identificados

### 2.1 Violação de SRP — flowcore.py como Monólito

**Gravidade:** Alta

`flowcore.py` tinha 1582 linhas contendo:
- Parsing de CLI
- Lógica de negócio (importar, buscar, sincronizar)
- Acesso direto ao SQLite (8+ cópias do mesmo padrão)
- Acesso ao sistema de arquivos para memórias
- Chamadas HTTP ao Ollama
- Formatação de saída no terminal

Isso viola Single Responsibility e impossibilita testes unitários isolados.

### 2.2 Duplicação Crítica — Padrão DB repetido 8 vezes

**Gravidade:** Alta

O seguinte bloco aparecia em cmd_import, cmd_docs, cmd_show, cmd_note, cmd_todo,
cmd_agenda, cmd_search, cmd_daily, e cmd_stats:

```python
cfg = get_config()
db_url = cfg.get("database", {}).get("url", "sqlite+aiosqlite:///data/flowcore.db")
db_path = db_url.replace("sqlite+aiosqlite:///", "")
async with aiosqlite.connect(db_path) as db:
    # operação
```

**Resolução aplicada em Sprint 7:** Extraído para `storage/document_repo.py`.

### 2.3 Duas ORM Stacks para o Mesmo Banco

**Gravidade:** Média

- `runtime/core.py` usa SQLAlchemy (`create_async_engine`) para tabelas `flows` e `executions`
- `flowcore.py` usava `aiosqlite` diretamente para a tabela `documents`

Ambas apontam para `data/flowcore.db`. Risco de conflito de locking e inconsistência.
As tabelas `flows`/`executions` do SQLAlchemy nunca foram conectadas à API (que usa
um dict in-memory).

**Decisão:** Manter `aiosqlite` direto nas repositories de storage. SQLAlchemy ficará
restrito ao runtime de plataforma quando houver necessidade de ORM. Unificar no Sprint 8.

### 2.4 Bug: load_config() chamada com argumento

**Gravidade:** Média (crash silencioso em `python3 flowcore.py run`)

```python
# runtime/core.py — linha 104
self.cfg = load_config(self.root)  # ERRADO: load_config() não aceita argumentos
```

**Resolução aplicada em Sprint 7:** Corrigido para `load_config()`.

### 2.5 Bug: audit.py lê arquivo inexistente

**Gravidade:** Baixa (auditoria sempre falha no check 3)

```python
# scripts/audit.py — linha 88
config_path = ROOT / "config" / "default.yml"  # ERRADO: arquivo é .json
```

**Resolução aplicada em Sprint 7:** Corrigido para `config/default.json`.

### 2.6 Persistência Dual para Dados do Mesmo Domínio

**Gravidade:** Média

- Memórias: JSON em `~/.flowcore/memories.json`
- Documentos: SQLite em `data/flowcore.db`

Ambos são "conteúdo armazenado pelo usuário". Duas tecnologias de persistência
diferentes dificultam buscas unificadas e backup.

**Decisão:** Manter separação por ora. Sprint 8 avaliará migração de memórias para SQLite.

### 2.7 API usa Dict In-Memory (sem persistência)

**Gravidade:** Alta para produção, baixa para MVP

`api/router.py` usa `_flows = {}` e `_executions = {}`. Toda informação é perdida
no restart. O `runtime/core.py` cria tabelas SQLAlchemy para `flows` e `executions`
mas a API nunca as usa.

### 2.8 Scheduler com import de nível de módulo

**Gravidade:** Baixa

`scheduler/service.py` importa `apscheduler` no topo do módulo. Se o apscheduler
não estiver instalado, qualquer import de `scheduler.service` falhará. O padrão
do projeto é lazy import para dependências opcionais.

### 2.9 Ausência de Interfaces/Protocolos

**Gravidade:** Média

Não há `Protocol` ou `ABC` para:
- Providers de AI (Ollama, Claude, OpenAI)
- Bridges de plataforma (Android, Termux, Linux)
- Repositórios de storage

Isso torna a substituição difícil e viola Dependency Inversion.

---

## 3. O que Está Bem

| Componente          | Qualidade | Observação                                     |
|---------------------|-----------|------------------------------------------------|
| `executor/engine.py`| Alta      | Async correto, retry, timeout, semaphore       |
| `agents/base.py`    | Alta      | ABC limpo, AgentRegistry bem definido          |
| `config/loader.py`  | Alta      | Deep merge, env overrides, singleton           |
| `scheduler/service.py`| Alta   | Wrapper limpo sobre APScheduler                |
| Modelo de segurança | Alta      | Localhost only, sem root, sem injeção de shell |
| `storage/` (novo)   | Alta      | Repository pattern, sync wrappers, testável    |

---

## 4. Acoplamento por Camada

```
CLI (flowcore.py)
    ├── storage/ [novo — desacoplado]
    │     ├── DocumentRepository → aiosqlite
    │     └── MemoryRepository → JSON
    ├── runtime/core.py → SQLAlchemy (tabelas não conectadas à API)
    ├── executor/engine.py (standalone — ok)
    ├── agents/ (standalone — ok)
    ├── scheduler/service.py → apscheduler
    └── api/router.py → in-memory (não conectado ao executor)
```

**Problema principal:** A API não está conectada ao Executor nem ao Scheduler.
Os fluxos declarados via API não são executados por ninguém.

---

## 5. Avaliação SOLID

| Princípio | Status | Detalhe                                          |
|-----------|--------|--------------------------------------------------|
| SRP       | ⚠ Parcial | flowcore.py melhorou; API ainda mistura tudo   |
| OCP       | ✗     | Adicionar comando requer 3 modificações em flowcore.py |
| LSP       | ✓     | BaseAgent funciona corretamente                  |
| ISP       | ✓     | Interfaces pequenas onde existem                 |
| DIP       | ✗     | CLI importa aiosqlite/urllib diretamente         |

---

## Consequências

Esta revisão fundamenta o plano de 5 Sprints documentado em `docs/SPRINT_PLAN.md`.
As correções de Sprint 7 (storage layer, bug fixes) são pré-condição para todo
o trabalho subsequente.
