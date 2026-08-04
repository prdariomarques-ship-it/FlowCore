# FlowCore Runtime Architecture Spec (Sprint 3)

## 1. Objetivo do FlowCore Runtime
O **FlowCore Runtime** atua como o sistema operacional virtual e local para agentes inteligentes do FlowCore. Sua missão é traduzir as solicitações abstratas de capacidades (Capabilities) enviadas pelas IAs em ações físicas determinísticas executadas com total segurança contra o host local (Android + Termux), impedindo a exposição ou execução direta de comandos shell de baixo nível pela LLM.

## 2. Escopo
*   Mapeamento, priorização e alternância dinâmica de Runtimes através do `RuntimeManager`.
*   Encapsulamento de APIs do Android e do Termux através de Providers isolados.
*   Orquestração do ciclo de inicialização segura do runtime (`Boot Sequence`).
*   Suporte para falha segura e recuperação automatizada de erros (`Runtime Recovery`).
*   Emissão do cartão de trânsito específico de runtime: `flowcore.runtime.passport.json`.

## 3. Arquitetura em Camadas (Execution Stack)

```
FlowCore Brain (Agente / IA)
       ↓ (Intenção Abstrata: "Qual minha bateria?")
Reasoning Engine
       ↓
Context Engine (Valida permissões e estado READY do ambiente)
       ↓
Execution Engine (Dispara getBattery() à camada de runtime)
       ↓
Runtime Manager (Seleciona o melhor runtime ativo)
       ↓
Android / Termux Runtime (Dispara a solicitação para o Provider de bateria correspondente)
       ↓
Battery Provider (Conversa com o BatteryManager do Android ou Termux API)
       ↓
Termux API / Sistema Android (S.O. Local)
```

## 4. Estrutura de Diretórios Proposta
A estrutura física de módulos segue o seguinte design modular:

```
flowcore/
└── runtime/
    ├── __init__.py
    ├── runtime_manager.py       # Descoberta, priorização e gerência de runtimes
    ├── runtime_boot.py          # Orquestrador da Boot Sequence
    ├── runtime_health.py        # Validação física e diagnósticos (disk, memory)
    ├── runtime_state.py         # Estados possíveis do runtime
    ├── runtime_context.py       # Contexto e emissor do runtime.passport
    ├── runtime_logger.py        # Sistema de telemetria e logs seguros
    ├── android/
    │   ├── __init__.py
    │   ├── battery.py           # Provider de Bateria via APIs Android
    │   ├── wifi.py              # Provider de Wi-Fi
    │   └── clipboard.py         # Provider de Área de transferência
    └── termux/
        ├── __init__.py
        ├── termux_api.py        # Wrapper central da Termux API
        ├── shell.py             # Emulador de execução isolada do shell
        └── python.py            # Executador e gerenciador de pacotes pip
```

---

## 5. Interfaces Públicas e Contratos

### `RuntimeManager`
*   **Entrada:** `workspace_path: Path`
*   **Saída:** `IRuntime` (o runtime priorizado e ativo para o host atual)
*   **Contrato:** Mantém o registro de todos os runtimes disponíveis (Android, Termux, Linux, etc.), valida qual é o runtime mais adequado e ativa-o dinamicamente.

### `IRuntime` (Base Interface)
*   **Contrato:** Deve implementar `boot()`, `health_check()`, `execute_capability(capability_name, **kwargs)` e reportar seu status operacional.

---

## 6. Formato Oficial de `flowcore.runtime.passport.json`
O arquivo de passaporte de runtime é gerado na raiz do workspace a cada inicialização bem-sucedida da boot sequence:

```json
{
  "$schema": "https://flowcore.io/schemas/runtime-passport.v1.json",
  "runtime_id": "termux_runtime_01",
  "runtime_version": "4.0",
  "platform": "Android/Termux",
  "providers": ["battery", "wifi", "clipboard", "python"],
  "health": {
    "status": "HEALTHY",
    "disk": "OK",
    "memory": "OK"
  },
  "permissions": {
    "storage": "GRANTED",
    "termux_api": "GRANTED"
  },
  "capabilities": ["getBattery", "getWifi", "installPythonPackage"],
  "boot_time": "2026-08-02T12:00:00Z",
  "last_health_check": "2026-08-02T12:00:05Z",
  "status": "READY"
}
```

---

## 7. Architecture Decision Records (ADRs)

### ADR-005 - FlowCore Runtime
#### Status
**APPROVED**
#### Contexto
A LLM não deve ter capacidade para disparar comandos arbitrários CLI diretament no terminal local, pois isso gera alto risco de segurança e dependência de sintaxes específicas de sistema.
#### Decisão
Adotar a abstração do **FlowCore Runtime** que age como uma ponte síncrona. A IA solicita apenas intenções puras (`capabilities`) e o Runtime resolve para o provider correto.
#### Vantagens
* Proteção contra deleções acidentais e injeções bash.
* Total portabilidade do código dos agentes.

### ADR-006 - Runtime Providers
#### Status
**APPROVED**
#### Contexto
Diferentes sistemas possuem canais distintos para resolver uma mesma capacidade (ex: bateria no Termux necessita de `termux-battery-status`, enquanto no macOS requer `pmset`).
#### Decisão
Utilizar o padrão de projeto **Provider**, onde cada Runtime registra múltiplos provedores especializados para mapear as chamadas abstratas aos recursos de baixo nível do S.O.
#### Vantagens
* Desacoplamento total entre o core do FlowCore e os comandos do sistema.

### ADR-007 - Android Runtime
#### Status
**APPROVED**
#### Contexto
O celular Android possui serviços e métricas restritas por sandbox nativo.
#### Decisão
Disponibilizar o `AndroidRuntime` especializado para consultar a bateria, o Wi-Fi e as permissões de armazenamento nativas utilizando o invólucro do Android SDK quando aplicável.

### ADR-008 - Termux Runtime
#### Status
**APPROVED**
#### Contexto
No ambiente Linux fornecido pelo Termux no celular, os comandos de terminal, gerenciadores de pacotes e a ponte `Termux API` são os canais nativos de infraestrutura.
#### Decisão
Implementar o `TermuxRuntime` focado em rodar scripts python, comandos git, e consumir a suite `termux-api` de forma higienizada.
