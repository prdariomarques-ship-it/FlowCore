# FlowCore Runtime Lifecycle Specification

## 1. Ciclo de Vida do Runtime Integrado
Os adaptadores de Runtime (ex: Android Runtime, Termux Runtime, Linux Runtime, etc.) seguem um ciclo de vida síncrono e coordenado diretamente pelo **Runtime Manager** sob as ordens do Kernel.

---

## 2. ADR-011 — Runtime Lifecycle
*   **Status:** APPROVED
*   **Contexto:** Evitar que runtimes comecem a carregar recursos ou acessar o hardware se as permissões locais não tiverem sido aprovadas, ou se o ambiente estiver corrompido, gerando falhas catastróficas de execução de IAs.
*   **Decisão:** Vincular o ciclo de vida do Runtime ao fluxo do Bootloader do Kernel de forma atômica e sequencial. O Runtime entra em status `NOT_READY`, transita por `LOADING`, `VALIDATING`, e só alcança `READY` se todas as permissões forem verificadas síncronamente.
*   **Vantagens:** Segurança total, previsibilidade no fluxo de execução de intenções e blindagem contra erros silenciosos do celular.
*   **Limitações:** Runtimes bloqueados por falhas não podem ser burlados pelas LLMs (recurso de segurança intencional).
