# Transição operacional do FlowCore

## Regra de aceitação

Nenhum recurso será considerado concluído apenas porque está no código. O estado operacional deve ser classificado como **demonstrado**, **pronto para instalação** ou **pendente de ação no dispositivo**. A evidência deve registrar endpoint, resposta, data e ambiente do teste.

## Inventário atual

| Ativo | Local principal | Estado de preservação | Dependência operacional |
|---|---|---|---|
| Backend FlowCore | GitHub `prdariomarques-ship-it/FlowCore` | Versionado no branch `claude/flowcore-architecture-consolidation-h95fi2` | Termux e Python no Android |
| Mercado e briefing | Código `runtime/market_intelligence` do FlowCore | Versionado e testado localmente contra dados reais | `yfinance`, internet e atualização do clone Termux |
| Dashboard web | `web/index.html` no FlowCore | Versionado no GitHub | FlowCore na porta 8080 e Cloudflare Tunnel |
| Túnel público | Cloudflare | Configuração fora do repositório | Token privado no Termux |
| Bots Telegram | Scripts privados no Termux | Não versionar tokens | `~/.flowcore/bots/*.sh`, token privado e rede |
| APK FlowCore Mobile | Projeto `flowcore-mobile` e checkpoint `3b32120d` | Checkpoint e arquivos do projeto | Gerar e guardar APK localmente |
| Conexão privada | Tailscale | Administração fora do repositório | Novo computador autenticado e aprovado |

## Pacote que deve existir fora do Manus

Mantenha cópias independentes em local sob seu controle: clone atualizado do repositório GitHub, arquivo APK gerado, pasta de configurações não sensíveis, scripts de boot do Termux, lista dos dispositivos Tailscale e documentação de manutenção. Tokens do Cloudflare, Telegram e Tailscale não devem entrar no Git, em APKs, arquivos públicos ou conversas.

## Backup do projeto Manus

O aviso recebido no aplicativo e no e-mail da conta é a fonte de verdade para saber se a conta está no escopo da mudança de serviço. Se estiver afetada ou houver dúvida, faça o backup de dados de tarefas pelo fluxo **Export task data → Export more → All tasks → All time → Start export** em [manus.im/backup](https://manus.im/backup). O export é um retrato pontual: mudanças posteriores não entram automaticamente no pacote [1].

O backup de um projeto mobile preserva código, checkpoints, configuração, dados e histórico de build, mas não deve ser tratado como garantia de arquivamento de todo APK já compilado. Guarde uma cópia local do arquivo de instalação quando ele for gerado [2]. Para projetos web, um download de código isolado também não substitui um backup de tarefa, pois banco, arquivos, configurações e integrações podem ficar fora dele [3].

## Evidência mínima para declarar o aplicativo funcional

1. Termux sincronizado com o commit do FlowCore e `requirements-api.txt` instalado.
2. `https://flowcore.admissaoazusa.com.br/api/market/overview` responde HTTP 200 com itens reais.
3. `https://flowcore.admissaoazusa.com.br/api/market/briefing` responde HTTP 200 com o mesmo briefing disponível aos bots.
4. APK gerado, instalado no Android e aba Mercado exibindo os itens da API.
5. Teste na aba Conexão confirma Cloudflare; após cadastrar o novo computador, confirma Tailscale ou executa fallback ao Cloudflare.

## Referências

[1]: https://help.manus.im/en/articles/16147892-service-change-overview-how-to-back-up-your-data "Manus — How to Back Up Your Data"
[2]: https://manus.im/backup "Manus — Data Backup Tool"
[3]: https://help.manus.im/en/articles/16147895-service-change-overview-how-to-restore-your-data "Manus — How to Restore Your Data"
