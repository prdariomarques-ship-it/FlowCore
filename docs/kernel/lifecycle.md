# FlowCore Platform Lifecycle Specification

## 1. Máquina de Estados Finita (FSM) de Ciclo de Vida do Kernel
O ciclo de vida do FlowCore é regido por uma máquina de estados finita rigorosa. O **Lifecycle Manager** do Kernel monitora e transiciona o sistema operacional virtual entre as seguintes fases:

```
  [CREATED]
      ↓
  [BOOTING]
      ↓
  [READY] ────→ [RUNNING] <────→ [PAUSED]
                  │   │
                  │   └────────→ [RECOVERING] / [UPDATING]
                  ▼
  [STOPPING] ────→ [STOPPED]
                  │
                  ▼
              [FAILED]
```

## 2. Definição dos Estados Oficiais:
*   **CREATED:** Instância do Kernel criada na memória do processo local, nenhum recurso alocado ainda.
*   **BOOTING:** O `BootManager` está carregando os registros essenciais e executando a sequência de diagnósticos síncronos do host.
*   **READY:** O Bootloader completou todas as auditorias sem erros. A barreira está aberta e o sistema está pronto para receber ações.
*   **RUNNING:** Serviços ativos e processamento de intenções/workflows em andamento.
*   **PAUSED:** Agendamentos de tarefas suspensos temporariamente.
*   **STOPPING:** Encerramento ordenado de conexões e gravação física de logs de auditoria finais.
*   **STOPPED:** Encerramento concluído. Nenhum serviço ativo.
*   **FAILED:** Falha estrutural insanável detectada no host (ex: erro físico de disco ou falta de permissões de sandbox).
*   **RECOVERING:** Componente de recuperação síncrona de falhas ativo para restaurar o estado operacional saudável.
*   **UPDATING:** Atualizador ativado para atualizar binários e esquemas com rollback seguro de transação.
