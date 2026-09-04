# Design de interface — FlowCore Mobile

## Propósito

O FlowCore Mobile será uma interface financeira de uso diário para leitura de mercado, carteira-modelo e exposição a inteligência artificial. A aplicação não executará ordens. Ela apresentará dados, timestamps, alertas e propostas de revisão, mantendo o usuário no controle da decisão.

O desenho assume orientação retrato 9:16, interação com uma mão e padrão de aplicativo financeiro nativo. O conteúdo prioritário fica na metade superior da tela; a navegação inferior usa quatro destinos principais e a configuração técnica fica fora do fluxo de leitura diária.

## Telas

| Tela | Conteúdo e funcionalidade | Ação primária |
|---|---|---|
| **Visão** | Estado de conexão, atualização mais recente, resumo de mercado, regime macro e alertas prioritários. | Atualizar dados e abrir o detalhe de mercado. |
| **Mercado** | Principais índices, moedas, juros, commodities, notícias e agenda econômica recebidos da API central do FlowCore. | Alternar grupos e abrir detalhes de um ativo. |
| **Carteira** | Total de referência, alocação por classe, detalhamento da carteira moderada e revisão por eventos. | Revisar desvios e registrar a necessidade de decisão humana. |
| **IA** | Exposição alvo, faixa de risco, subtemas, eventos de resultados, guidance e regulação. | Revisar a parcela temática. |
| **Conexão** | Endpoint Cloudflare público, endpoint Tailscale privado, indicador de origem e última falha. | Testar e selecionar o endpoint preferido. |

## Fluxos principais

O fluxo de leitura começa na tela **Visão**, onde o usuário identifica se os dados chegaram recentemente e enxerga os alertas mais importantes. Um toque no resumo de mercado leva à tela **Mercado**, que mostra índices e blocos de informação na mesma estrutura usada pelos bots Telegram.

O fluxo de carteira começa em **Carteira**. O usuário revisa o alvo de R$ 1 milhão, vê desvios e eventos recebidos e pode solicitar uma análise. A interface declara que o resultado é informacional e que nenhuma ordem é executada. A tela **IA** funciona como recorte temático da carteira, destacando concentração e gatilhos de risco.

O fluxo de conectividade começa na tela **Conexão**. O aplicativo tenta primeiro o endpoint preferido configurado pelo usuário e mantém alternativa entre Cloudflare e Tailscale. Ele informa a URL de origem de forma abreviada, nunca exibe token e mostra um estado explícito de conexão, atualização ou falha.

## Direção visual

| Elemento | Escolha |
|---|---|
| Fundo | Azul-noite `#08111F`, para reduzir fadiga em leituras de mercado. |
| Superfícies | Grafite-azulado `#122033`, com bordas `#223A58`. |
| Acento principal | Ciano financeiro `#20C6D8`, para dados ativos e conexão. |
| Crescimento | Verde `#34C38F`, para estado normal e variação positiva. |
| Atenção | Âmbar `#F2B84B`, para dado desatualizado e revisão necessária. |
| Risco | Coral `#F06B6B`, para falha de conexão ou alerta de risco. |
| IA | Lilás `#A78BFA`, reservado à exposição temática de inteligência artificial. |

Os cartões terão bordas discretas, tipografia numericamente legível e espaços de toque de pelo menos 44 pontos. Variações de preço jamais serão comunicadas apenas por cor: cada estado também terá texto e sinalização de direção.

## Princípios de dados e segurança

O app não utilizará números fictícios. Sem conexão, ele mostrará ausência ou último dado armazenado com timestamp. Cloudflare serve como entrada pública HTTPS; Tailscale é a rota privada alternativa entre dispositivos autorizados. Tokens, chaves e credenciais não aparecerão no APK, nas telas ou nos logs do app.
