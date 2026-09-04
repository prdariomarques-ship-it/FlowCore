# Validação de mercado ao vivo

Em 25 de agosto de 2026, o dashboard local do FlowCore foi aberto em `http://127.0.0.1:8080/` e exibiu dados reais pelo endpoint `GET /api/market/snapshot`.

| Campo exibido | Valor observado | Fonte |
|---|---:|---|
| USD/BRL PTAX | R$ 5,15 | Banco Central do Brasil — PTAX |
| Ibovespa | 174.576,8; +1,55% | Yahoo Finance |
| Selic | 13,9% a.a. | Banco Central do Brasil — SGS 1178 |
| IPCA acumulado em 12 meses | 4,44% | Banco Central do Brasil — SGS 13522 |

O carregamento inicial levou alguns segundos por depender de fontes externas, mas os valores foram renderizados em vez dos textos anteriores de espera. Quando uma fonte falhar, o contrato do endpoint retorna `null` naquele campo, a fonte, um timestamp e o erro de forma explícita; não há valor sintetizado.
