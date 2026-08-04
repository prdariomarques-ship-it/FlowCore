# FlowCore Microkernel Specification

## 1. Objetivo do FlowCore Kernel
O **FlowCore Kernel** é o núcleo de controle mínimo (Microkernel) que gerencia o ciclo de vida, serviços, plugins, barramento de eventos e registros essenciais da plataforma FlowCore. Ele é projetado para operar com o menor número possível de responsabilidades estritas no core, delegando todas as outras ações operacionais a serviços dinâmicos e adaptadores de runtime de modo a garantir estabilidade, segurança e portabilidade impecáveis.

## 2. Registros Oficiais da Plataforma
O Kernel orquestra as seguintes centrais de dados declarativas:
*   **Capability Registry:** Catálogo de capacidades abstratas resolvíveis (ex: `battery`, `wifi`).
*   **Runtime Registry:** Lista de ambientes de execução registrados (ex: `Android`, `Termux`, `Docker`).
*   **Service Registry:** Mapeamento de serviços ativos no barramento (ex: `DoctorService`, `SchedulerService`).
*   **Plugin Registry:** Registro de extensões dinâmicas de terceiros.
*   **Provider Registry:** Catálogo de provedores de hardware associados a runtimes específicos.
*   **Agent Registry:** Registro de agentes autorizados (Jules, Qwen, GLM, Claude, etc).
*   **Configuration Registry:** Central única e unificada de chaves e variáveis do sistema.

---

## 3. ADR-009 — FlowCore Kernel
*   **Status:** APPROVED
*   **Contexto:** Sistemas monolíticos de IA tendem a quebrar silenciosamente devido a alterações ambientais ou dependências mal-gerenciadas. É preciso uma fundação estável, isolada e baseada em Microkernel.
*   **Decisão:** Construir o FlowCore Kernel baseado na filosofia Microkernel (núcleo síncrono mínimo), delegando IO, telemetria, conexões e lógica a serviços acopláveis de forma plug-and-play.
*   **Vantagens:** Extrema resiliência, facilidade de auditoria e alta velocidade de boot.
*   **Limitações:** Necessidade de orquestração explícita via barramento de eventos síncronos/assíncronos.

---

## 4. ADR-013 — Registry System
*   **Status:** APPROVED
*   **Contexto:** Evitar dados de configuração perdidos ou dispersos no código dos adaptadores.
*   **Decisão:** Estabelecer registries unificados e baseados em estruturas de dicionários estritos do Python, permitindo consultas instantâneas síncronas.
*   **Vantagens:** Visibilidade centralizada e previsível de todos os recursos da plataforma.
