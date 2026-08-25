# Fontes de mercado — FlowCore

## Objetivo

O FlowCore não deve apresentar números sem indicar origem, data de observação e horário de coleta. A camada de mercado usa fontes oficiais quando há cobertura direta, mantém Yahoo Finance como fallback de cotações globais e deixa TradingEconomics como integração opcional autenticada. WSJ é referência editorial e de verificação, não fonte automatizada sem licença e acesso apropriados.

## Catálogo operacional

| Fonte | Papel | Cobertura inicial | Credencial | Estado |
|---|---|---|---|---|
| Banco Central do Brasil — BCData/SGS | Primária oficial | Selic e séries macro brasileiras | Não | Integrada |
| U.S. Department of the Treasury | Primária oficial | Curva PAR 2Y, 5Y, 10Y e 30Y | Não | Integrada com timeout e status explícito |
| Yahoo Finance | Fallback de mercado | Índices, FX, commodities e bolsas | Não | Mantida |
| TradingEconomics | Fonte complementar | Mercados, calendário e histórico | `FLOWCORE_TRADING_ECONOMICS_KEY` | Catálogo pronto; exige credencial |
| Wall Street Journal | Referência editorial | Contexto e verificação de notícias | Não automatizar | Referência manual |

## Regras de exibição

Cada observação retornada para dashboard, Telegram e APK precisa conter `source`, `observation_date`, `retrieved_at`, unidade e status. Uma fonte lenta ou indisponível não pode bloquear o feed: o sistema retorna a ausência de dado daquela fonte e mantém as demais observações. Divergências materiais devem aparecer como divergência de base, horário ou instrumento — nunca como média implícita de cotações.

## Evidência de integração

Em 25 de agosto de 2026, a consulta BCData/SGS retornou Selic de 13,90% para a série 1178. A tabela diária do Tesouro dos EUA respondeu com os campos de curva PAR; a disponibilidade pode variar por rede e por isso o serviço limita o tempo de espera e reporta falha explícita, sem substituir por dado inventado.

## Referências

[1]: https://api.bcb.gov.br/dados/serie/bcdata.sgs.1178/dados/ultimos/3?formato=json "Banco Central do Brasil — BCData/SGS, série 1178"
[2]: https://dadosabertos.bcb.gov.br/ "Banco Central do Brasil — Dados Abertos"
[3]: https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics "U.S. Treasury — Interest Rate Statistics"
[4]: https://docs.tradingeconomics.com/ "TradingEconomics API Documentation"
[5]: https://finance.yahoo.com/ "Yahoo Finance"
