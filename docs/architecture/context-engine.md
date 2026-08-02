# Architecture Freeze: Context Engine

## 1. Objetivo do Context Engine
O **Context Engine** é o mecanismo orquestrador de inteligência de contexto do FlowCore. Seu objetivo primário é analisar e validar automaticamente o ambiente, a infraestrutura e a árvore de diretórios de qualquer repositório de trabalho *antes* que qualquer agente de Inteligência Artificial inicie auditorias, correções ou implementações. Ele garante que a IA opere sob um estado determinístico e mapeado com precisão, minimizando alucinações e impedindo alterações destrutivas em contextos incorretos ou incompatíveis.

## 2. Escopo
O escopo do Context Engine abrange:
*   A varredura recursiva de diretórios dentro da raiz do workspace (`/workspace`).
*   A classificação automática do ecossistema do projeto (tecnologias, frameworks e propósitos).
*   A detecção de assinaturas de artefatos estruturais (ex: manifestos, gerenciadores de pacotes).
*   A análise de capacidades e recursos locais (infraestrutura e integrações).
*   A validação da disponibilidade de dependências e runtimes do sistema local.
*   A análise de risco de impacto de qualquer alteração de código.
*   A geração de um cartão de contexto versionado (`flowcore.context.json`) definindo o status do ambiente.

## 3. Responsabilidades
*   **Mapeamento de Workspace:** Identificar com segurança o diretório atual, a raiz do workspace e validar permissões de acesso ao disco.
*   **Classificação de Tecnologias:** Identificar e categorizar o projeto sob uma ou mais classificações conhecidas (ex: Python, Android, Node, CLI, Backend).
*   **Identificação de Artefatos:** Localizar com exatidão arquivos chave e manifestos para validar a integridade.
*   **Emissão de Status de Pronto (READY):** Garantir que a IA somente receba autorização para alterar código se o status consolidado do ambiente for `READY`.
*   **Geração de Contexto Estruturado:** Serializar os dados da varredura em um formato JSON estrito, auto-contido e consumível por LLMs.

## 4. O Que NÃO é Responsabilidade do Context Engine
*   **Execução de Tarefas de Negócio:** Executar lógica de workflows, agendamentos de tarefas ou disparos de agentes do FlowCore.
*   **Instalação Automática de Dependências Globais:** O motor apenas detecta e valida a presença (ou ausência) das ferramentas; ele não deve alterar as variáveis globais do sistema ou instalar pacotes a nível de sistema de forma arbitrária.
*   **Correção Automática de Bugs de Código:** Corrigir erros de sintaxe ou lógica no código-fonte sob análise (isso é responsabilidade dos agentes corretores).

## 5. Fluxo Completo

O fluxo de processamento é estritamente sequencial e síncrono:

```
Usuário
  ↓
Context Engine (Orquestrador)
  ↓
Workspace Scanner (Mapeamento de raiz e permissões de sandbox)
  ↓
Project Classifier (Classificação heurística de ecossistema)
  ↓
Artifact Detector (Coleta e verificação de assinaturas e manifestos)
  ↓
Capability Detector (Descoberta de integrações e infraestrutura como SQLite, daemon)
  ↓
Dependency Graph (Mapeamento de imports estáticos e entrypoints)
  ↓
Environment Validator (Verificação de runtimes locais como python, node, etc.)
  ↓
Risk Analysis (Análise de impacto e sugestão de rollback das alterações propostas)
  ↓
AI Context Card (Serialização no arquivo flowcore.context.json)
  ↓
STATUS READY / BLOCKED / FAILED
```

## 6. Interfaces Públicas

### ContextEngine
*   **Entradas:** `workspace_path: Path`, `force_refresh: bool = False`
*   **Saídas:** `ContextFrame`
*   **Exceções:** `InvalidWorkspaceError`, `ScannerTimeoutError`
*   **Contratos:** Executa sequencialmente o pipeline configurado. Retorna o estado final do contexto consolidado.

### WorkspaceScanner
*   **Entradas:** `frame: ContextFrame`
*   **Saídas:** `ContextFrame`
*   **Exceções:** `PermissionDeniedError`, `WorkspaceNotFoundError`
*   **Contratos:** Deve extrair e mapear com segurança o diretório atual e a raiz do repositório, validando limites de escrita do sandbox.

### ProjectClassifier
*   **Entradas:** `frame: ContextFrame`
*   **Saídas:** `ContextFrame`
*   **Exceções:** Nenhuma (deve falhar graciosamente populando classificações vazias caso nada seja reconhecido).
*   **Contratos:** Aplica matriz de regras para rotular o repositório em uma ou mais categorias pré-definidas (ex: Python, CLI, Backend).

### ArtifactDetector
*   **Entradas:** `frame: ContextFrame`
*   **Saídas:** `ContextFrame`
*   **Exceções:** `ManifestCorruptionError` (se arquivos estruturais encontrados como JSON ou YAML estiverem corrompidos).
*   **Contratos:** Varre recursivamente diretórios não ignorados procurando assinaturas específicas e preenchendo a lista de artefatos.

### CapabilityDetector
*   **Entradas:** `frame: ContextFrame`
*   **Saídas:** `ContextFrame`
*   **Exceções:** Nenhuma.
*   **Contratos:** Identifica recursos suportados no ambiente (ex: suporte a sqlite ao encontrar bibliotecas python como `aiosqlite` ou `sqlite3`).

### DependencyGraph
*   **Entradas:** `frame: ContextFrame`
*   **Saídas:** `ContextFrame`
*   **Exceções:** `CircularDependencyWarning` (não-bloqueante).
*   **Contratos:** Constrói um mapa de acoplamento entre arquivos e módulos internos.

### EnvironmentValidator
*   **Entradas:** `frame: ContextFrame`
*   **Saídas:** `ContextFrame`
*   **Exceções:** `MissingRequiredRuntimeError` (se um runtime estritamente necessário estiver ausente).
*   **Contratos:** Confirma a versão e disponibilidade física de binários no path.

### RiskAnalyzer
*   **Entradas:** `frame: ContextFrame`, `proposed_changes: List[Dict[str, Any]]`
*   **Saídas:** `ContextFrame` (contendo relatório de riscos)
*   **Exceções:** `HighRiskBlockedError`
*   **Contratos:** Estima a área de impacto e atribui um score de risco de regressão.

### ContextSerializer
*   **Entradas:** `frame: ContextFrame`
*   **Saídas:** `ContextFrame` (gravando fisicamente o arquivo `flowcore.context.json`)
*   **Exceções:** `SerializationError`
*   **Contratos:** Converte o estado contido no `ContextFrame` em um JSON estruturado estrito e versionado.

### ContextCache
*   **Entradas:** `workspace_path: Path`
*   **Saídas:** `Optional[ContextFrame]`
*   **Exceções:** Nenhuma.
*   **Contratos:** Recupera e armazena estados computando hashes SHA-256 rápidos de arquivos chave.

## 7. Estados Possíveis do Context Engine

*   `NOT_READY`: Estado inicial do motor, nenhum scan executado ainda.
*   `SCANNING`: Ativo durante a varredura física de arquivos no disco pelo `WorkspaceScanner` e `ArtifactDetector`.
*   `VALIDATING`: Ativo durante a execução de classificações, validações de dependências e análise de ambiente.
*   `READY`: Indica que todas as validações obrigatórias foram concluídas com absoluto sucesso e que o ambiente está seguro para receber implementações.
*   `BLOCKED`: Indica que uma inconsistência crítica de segurança ou de escopo foi detectada (ex: falta de permissões de escrita ou incompatibilidade insanável do workspace).
*   `FAILED`: Ocorreu uma exceção ou falha interna inesperada durante a execução do pipeline.

## 8. Formato Oficial do Arquivo `flowcore.context.json`

O arquivo `flowcore.context.json` é gravado na raiz do workspace e segue rigidamente a seguinte especificação/schema:

```json
{
  "$schema": "https://flowcore.io/schemas/context.v1.json",
  "schema_version": "1.0.0",
  "validated": true,
  "project": "FlowCore Core",
  "language": "Python",
  "runtime": "Python 3.12",
  "type": [
    "Backend",
    "CLI",
    "Service"
  ],
  "capabilities": [
    "daemon",
    "sqlite"
  ],
  "workspace": "/workspace",
  "status": "READY",
  "timestamp": "2026-03-30T12:00:00Z"
}
```

## 9. Critérios de Sucesso
*   O Context Engine somente poderá retornar o status consolidado de `READY` se todas as validações obrigatórias configuradas forem executadas sem disparar exceções bloqueantes.
*   Qualque falha de segurança (permissão ou sandbox) deve transitar imediatamente o estado para `BLOCKED`.
*   O arquivo `flowcore.context.json` deve ser gravado com sucesso e validar contra o formato definido.

## 10. Architecture Decision Record (ADR-001)

### Context Engine - Garantia de Contexto de IA

#### Status
**PROPOSED & APPROVED**

#### Contexto
Agentes de IA trabalhando em workspaces complexos e em múltiplos projetos podem sofrer de alucinações contextuais, editar arquivos fora do escopo do repositório correspondente ou tentar modificar runtimes incompatíveis, gerando regressões críticas. É necessário um mecanismo que faça uma auditoria rápida, síncrona e hermética do workspace antes que qualquer agente modifique código.

#### Decisão
Projetar e construir o **Context Engine**, um pipeline síncrono e estruturado executado a cada inicialização de agente. Ele persistirá seu veredito em `flowcore.context.json` na raiz do workspace.

#### Alternativas Consideradas
*   *Alternativa 1: Varredura de arquivos em lote sob demanda integrada nos prompts.* (Rejeitada porque adiciona latência, consome muitos tokens e não fornece garantias estruturadas/programáticas).
*   *Alternativa 2: Confiança exclusiva em scripts shell legados como doctor.sh.* (Rejeitada por não ser facilmente programável ou legível para agentes de IA de forma integrada em JSON).

#### Vantagens
*   Garante que o workspace atual está mapeado de forma exata e estruturada antes que a IA aja.
*   Segurança contra edição acidental em sandboxes restritos.
*   Velocidade por meio de arquitetura leve e cache SHA-256.

#### Limitações
*   A varredura estática de acoplamento pode ser lenta em monorepos gigantescos (mitigado pelo `ContextCache` e limites de profundidade).

#### Impactos Futuros
*   Facilidade de acoplamento com novos ecossistemas e novas ferramentas de auditoria contínua (CI/CD local).
