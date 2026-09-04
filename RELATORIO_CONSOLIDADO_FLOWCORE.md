# Relatório consolidado do FlowCore

**Autor:** Manus AI  
**Data:** 25 de agosto de 2026  
**Branch:** `claude/flowcore-architecture-consolidation-h95fi2`  
**Commit publicado:** `80c22be`

## 1. Objetivo e resultado executivo

O FlowCore foi reorganizado para deixar a visão inicial centrada em informação financeira e inteligência artificial, retirando da tela principal os diagnósticos de bateria, daemon e notificações. Esses componentes continuam disponíveis na tela **Admin**, onde fazem sentido operacionalmente. Também foi implementada uma carteira-modelo moderada de **R$ 1.000.000**, com exposição satélite de **7% ao tema de inteligência artificial**, subdivisões de renda fixa brasileira e internacional, multimercados, renda variável e alternativos.

A revisão diária foi implementada como mecanismo **informacional e orientado por eventos**. Ela compara alvos com posições informadas, identifica desvios e registra eventos relevantes, mas não envia ordens, não compra, não vende e sempre exige aprovação humana. A implantação pública existente do Cloudflare respondeu HTTP 200 no endpoint de saúde durante a validação; entretanto, a nova versão do código ainda precisa ser sincronizada no Termux para aparecer no hostname público.

> **Estado atual:** o código novo está no GitHub e foi validado localmente. O Cloudflare está saudável e apontando para o FlowCore do celular. A etapa pendente para refletir esta versão na URL pública é atualizar o clone no Termux, reinstalar o `tools/boot.sh` atualizado e reiniciar os serviços.

## 2. Alterações de interface

A antiga visão inicial concentrava estatísticas técnicas, daemon e notificação Android. Ela agora apresenta quatro blocos úteis para acompanhamento: visão financeira, mercado, macro e IA no portfólio. Como as fontes de mercado ainda não foram configuradas, os cartões exibem explicitamente “aguardando fonte” ou “sem dados”, em vez de inventar cotações, regimes ou indicadores.

| Tela | Conteúdo | Estado |
|---|---|---|
| **Visão** | Carteira-modelo, exposição IA, renda fixa, mercado e macro | Nova visão financeira |
| **Carteira** | 18 subdivisões, alocação agregada e revisão diária | Funcionando com dados de referência |
| **IA** | R$ 70 mil de referência, faixa 4%–10%, subtemas e gatilhos | Nova tela |
| **Admin** | Bateria, armazenamento, Passport, daemon e notificação | Diagnóstico técnico concentrado |
| **Memórias** | Memórias persistentes | Mantida |
| **Agentes** | Agentes, tarefas e flows | Mantida |

A navegação técnica anterior “Sistema” foi substituída por **Admin**. Os elementos técnicos não são mais renderizados na página inicial. Durante a validação visual, a tela inicial não mostrou bateria, daemon nem notificação, enquanto as telas de IA e Carteira carregaram corretamente.

## 3. Carteira moderada de R$ 1 milhão

A especificação foi gravada em `config/portfolio_moderate_1m.json`. A soma dos pesos é **100%** e a soma dos valores nominais é **R$ 1.000.000**. Os valores são alvos de referência, não posições reais e não constituem recomendação individual.

| Bloco | Subdivisões | Peso | Valor de referência |
|---|---|---:|---:|
| Renda fixa Brasil | Liquidez 10%; oportunidade 5%; pós-fixado 12%; prefixado 6%; IMA-B 5 6%; IMA-B 5+ 6% | **45%** | **R$ 450.000** |
| Renda fixa internacional | US Treasuries 7%; Global Bonds 5%; Corporate Bonds investment grade 3% | **15%** | **R$ 150.000** |
| Multimercados | Fundos multimercados / hedge funds | **10%** | **R$ 100.000** |
| Renda variável Brasil | Fundos de ações Brasil | **8%** | **R$ 80.000** |
| Renda variável global | Ações globais diversificadas | **10%** | **R$ 100.000** |
| Tema IA | Semicondutores, nuvem, infraestrutura e software por veículo amplo e diversificado | **7%** | **R$ 70.000** |
| Alternativos | FIIs 2,5%; ouro 1,5%; criptoativos 0,5%; stablecoin 0,25%; prata/paládio/cobre 0,25% | **5%** | **R$ 50.000** |
| **Total** | 18 subdivisões | **100%** | **R$ 1.000.000** |

A classificação de IMA-B foi alinhada à metodologia da ANBIMA: o IMA-B é segmentado em IMA-B 5 e IMA-B 5+, e o grupo 5+ representa títulos com vencimento igual ou superior a cinco anos [1]. Tesouro IPCA+ foi tratado como instrumento de proteção real sujeito à marcação a mercado antes do vencimento, enquanto Tesouro Prefixado foi tratado como instrumento com taxa nominal definida na contratação, também sujeito a oscilações de preço antes do vencimento [2] [3].

A exposição a IA foi desenhada como parcela satélite, e não como núcleo da carteira. O alvo é 7%, com faixa de alerta de 4% a 10% e limite de 2% por emissor. Essa disciplina evita transformar uma temática de crescimento e alta volatilidade em concentração excessiva.

## 4. Revisão diária baseada em eventos

A API agora oferece `GET /api/portfolios/moderate-ia-1m/review` para a revisão padrão e `POST /api/portfolios/moderate-ia-1m/review` para receber eventos e uma alocação atual. O algoritmo compara cada posição com o alvo, calcula o desvio em pontos percentuais e marca como fora da banda quando o desvio absoluto é de pelo menos **3 pontos percentuais**. Os limites e gatilhos ficam registrados na própria especificação JSON.

| Gatilho | Tratamento implementado |
|---|---|
| Decisão ou comunicação de banco central | Registrar evento e solicitar revisão |
| Inflação ou emprego | Registrar evento e reavaliar duration e indexadores |
| Variação diária relevante de BRL/USD | Revisar exposição cambial e internacional |
| Movimento superior a 3% em índice amplo de ações | Revisar risco e desvios |
| Evento de crédito, emissor, fundo ou contraparte | Gerar alerta de risco |
| Resultado, guidance ou regulação em IA | Revisar a parcela temática |
| Reserva de liquidez abaixo do piso | Gerar alerta prioritário |
| Faixa de classe fora do limite | Propor revisão e exigir aprovação humana |

A regra foi deliberadamente implementada como **review-and-alert-only**. Mesmo quando há evento ou desvio, a resposta da API registra `orders_executed: false` e orienta a avaliação humana. Não há integração de execução de ordens nesta versão.

## 5. APIs implementadas

Os endpoints de portfólio deixaram de retornar listas vazias. Eles agora leem a configuração versionada, expõem as 18 subdivisões, agregam pesos por classe e produzem o estado de revisão.

| Endpoint | Função |
|---|---|
| `GET /api/portfolios` | Inclui a carteira-modelo mesmo que não exista uma carteira persistida do usuário |
| `GET /api/portfolios/moderate-ia-1m` | Retorna a configuração completa |
| `GET /api/portfolios/moderate-ia-1m/summary` | Retorna alvos e valores de referência |
| `GET /api/portfolios/moderate-ia-1m/exposure` | Agrega exposição por classe |
| `GET /api/portfolios/moderate-ia-1m/decision` | Retorna riscos, oportunidades e estado de prontidão |
| `GET /api/portfolios/moderate-ia-1m/narrative` | Retorna narrativa e política de revisão |
| `GET /api/portfolios/moderate-ia-1m/review` | Executa revisão informacional padrão |
| `POST /api/portfolios/moderate-ia-1m/review` | Avalia eventos e desvios enviados pelo operador |

## 6. Persistência no Termux, Cloudflare e bots

O `tools/boot.sh` já tinha loops de reinício para FlowCore e cloudflared. Esses loops foram preservados e o script foi ampliado para iniciar scripts executáveis em `~/.flowcore/bots/*.sh`. Cada bot recebe seu próprio log em `~/.config/flowcore/<nome-do-bot>.log` e é reiniciado dez segundos após uma saída. Os tokens não devem ser colocados no repositório; devem permanecer na configuração privada de cada bot ou no ambiente do Termux.

A busca no repositório não encontrou código de bot Telegram versionado. Portanto, o boot agora oferece um mecanismo seguro e genérico, mas a operação dos bots depende de os arquivos executáveis existirem no celular. O mecanismo não inventa nomes, não cria tokens e não executa arquivos que não estejam explicitamente instalados como executáveis pelo usuário.

Para sincronizar a versão no celular, o procedimento é:

```bash
cd ~/FlowCore
git fetch origin
git checkout claude/flowcore-architecture-consolidation-h95fi2
git pull --ff-only origin claude/flowcore-architecture-consolidation-h95fi2
mkdir -p ~/.termux/boot
cp tools/boot.sh ~/.termux/boot/flowcore.sh
chmod 700 ~/.termux/boot/flowcore.sh
```

Depois, reinicie o processo pelo próprio boot ou execute o script manualmente. Para instalar um bot sem expor credenciais no Git, coloque um script executável, por exemplo `~/.flowcore/bots/meu-bot.sh`, e mantenha o token em arquivo privado ou variável de ambiente. O script de boot detectará esse arquivo no próximo início.

O túnel público `flowcore` permanece associado ao UUID `f974b439-a1b6-48cb-8ffc-78e9d0857651`, com hostname `flowcore.admissaoazusa.com.br` apontando para `http://localhost:8080`. Na verificação de 25 de agosto de 2026, `https://flowcore.admissaoazusa.com.br/api/health` respondeu HTTP 200, com `termux: true` e `android: true`. Isso confirma que o túnel e o FlowCore do celular estavam acessíveis naquele momento. Como o celular ainda serve a versão anterior até fazer `git pull`, a URL pública não deve ser usada como prova de que a nova interface já foi instalada.

## 7. Diagnóstico e pendências

A primeira tentativa de executar o servidor no ambiente de validação falhou por dependências ausentes, especialmente `loguru`; as dependências declaradas em `requirements-api.txt` foram então instaladas e o servidor respondeu normalmente. O teste local confirmou HTTP 200 para sumário, exposição, revisão e página HTML. O teste POST com eventos e desvios também respondeu HTTP 200 e produziu alertas sem executar ordens.

A mensagem “Sem ligação” exibida no cabeçalho durante a inspeção visual decorre do endpoint geral `/api/status` depender de componentes locais/configurações adicionais. Ela não impediu o carregamento das rotas da carteira. O detalhe deve ser interpretado como estado de integração e permanecer na área Admin; não é uma falha do módulo de carteira.

| Item | Situação | Ação necessária |
|---|---|---|
| Código da nova interface | Implementado e publicado | Sincronizar no Termux |
| Carteira de R$ 1 milhão | Implementada | Informar posições reais somente se desejar análise personalizada |
| Revisão por eventos | Implementada, sem ordens | Conectar uma fonte de dados e alimentar eventos |
| Cloudflare | Saudável na última verificação | Manter token privado e confirmar após reinício |
| Boot FlowCore/cloudflared | Implementado no repositório | Copiar novamente para `~/.termux/boot` |
| Bots Telegram | Mecanismo de boot implementado | Colocar scripts executáveis em `~/.flowcore/bots` |
| Outlook, MCP e WhatsApp | Não configurados ou incompletos | Permanecem fora da visão financeira até configuração |
| Dados de mercado/macro ao vivo | Ainda não configurados | Adicionar fonte confiável antes de usar alertas reais |

## 8. Referências e ressalvas

Este documento descreve uma implementação técnica e uma carteira de referência. Não é recomendação individual, promessa de retorno, ordem de compra ou venda, nem substitui suitability, análise de custos, tributação, liquidez, risco de crédito, risco cambial e validação com profissional habilitado. A CVM trata suitability como o dever de verificar a adequação de produtos, serviços e operações ao perfil do cliente [4].

## Referências

[1]: https://www.anbima.com.br/pt_br/informar/precos-e-indices/indices/ima.htm "ANBIMA — IMA"
[2]: https://www.tesourodireto.com.br/en/produtos/titulos/ipca-mais "Tesouro Direto — Tesouro IPCA+"
[3]: https://www.tesourodireto.com.br/en/produtos/titulos/prefixado "Tesouro Direto — Tesouro Prefixado"
[4]: https://conteudo.cvm.gov.br/legislacao/resolucoes/resol030.html "CVM — Resolução CVM 30"
