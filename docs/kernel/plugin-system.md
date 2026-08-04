# FlowCore Plugin Architecture Specification

## 1. Mecanismo de Extensabilidade Dinâmica
O sistema do FlowCore foi projetado para ser expansível de forma plug-and-play. O **Plugin Manager** carrega extensões dinâmicas (contidas em diretórios dedicados como `~/.flowcore/plugins/`) e as registra síncronamente na plataforma, disponibilizando novas capacidades e provedores de forma transparente.

---

## 2. ADR-012 — Plugin Architecture
*   **Status:** APPROVED
*   **Contexto:** Permitir que desenvolvedores de terceiros criem novos agentes, capacidades e adaptadores sem necessidade de alterar o código do core do repositório.
*   **Decisão:** Utilizar carregamento de módulos dinâmicos por meio do `importlib` nativo do Python, aplicando convenções estritas de interfaces de plugins.
*   **Vantagens:** Extensibilidade infinita, baixo acoplamento e isolamento de código secundário.
*   **Limitações:** Execução em sandbox. Se um plugin malicioso for carregado, ele roda sob as mesmas permissões do processo do Termux. (Mitigado por auditorias de hashes e assinaturas).
