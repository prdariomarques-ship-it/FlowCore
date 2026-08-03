# FlowCore Service Manager Specification

## 1. Ciclo de Vida dos Serviços de Sistema
O **Service Manager** é a engrenagem encarregada de gerenciar os estados de serviços que rodam de forma síncrona ou em background no FlowCore. Cada serviço (como o `DoctorService`, `SchedulerService` ou `LoggerService`) é isolado e deve responder aos seguintes comandos padrão de controle:

*   **Start:** Inicializa os recursos internos do serviço e o coloca no barramento.
*   **Stop:** Encerra a execução e limpa as conexões físicas abertas (ex: arquivos de banco de dados).
*   **Restart:** Recicla os recursos limpando estados corrompidos.
*   **Pause:** Suspende temporariamente a escuta de eventos.
*   **Resume:** Retoma a escuta ativa.
*   **Health:** Consulta métricas internas para verificar a integridade estrutural.
*   **Dependencies:** Mapeia quais outros serviços devem obrigatoriamente estar ativos antes de inicializar o atual.

---

## 2. Contrato de Interface Comum (`IService`)
Todos os serviços devem herdar e implementar o seguinte contrato estrito:

```python
class IService:
    def start(self) -> bool: ...
    def stop(self) -> bool: ...
    def pause(self) -> bool: ...
    def resume(self) -> bool: ...
    def get_health(self) -> Dict[str, Any]: ...
```
