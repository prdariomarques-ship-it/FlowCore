# FlowCore Event Bus Specification

## 1. Arquitetura de Comunicação Decapada
No FlowCore, **nenhum serviço ou runtime se comunica de forma direta**. Toda interação é mediada e distribuída através do **Event Bus** síncrono. Isso garante que novos plugins, agentes ou adaptadores possam ser acoplados ou removidos do sistema sem causar impactos em cascata no núcleo do sistema de arquivos.

```
[Componente A] ──(Dispara Evento: "boot.completed")──> [ Event Bus ] ──(Distribui)──> [Componente B]
```

## 2. ADR-010 — Event Bus
*   **Status:** APPROVED
*   **Contexto:** Chamadas de método diretas geram alto acoplamento temporal e de dados, dificultando a implementação de múltiplos runtimes concorrentes ou recuperação de falhas de rede.
*   **Decisão:** Adotar um padrão Mediator simplificado e síncrono (Event Bus) baseado em canais de tópicos (Topic-based pub/sub) usando estruturas limpas de callbacks.
*   **Vantagens:** Desacoplamento arquitetônico total, facilidade de loggar e auditar todas as interações e possibilidade de mocks rápidos em testes de unidade.
*   **Limitações:** Requer gerenciamento cuidadoso de loops infinitos se dois ouvintes dispararem eventos recursivamente.
