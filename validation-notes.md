# Notas de validação visual

- O Expo web iniciou corretamente no endereço temporário e renderizou a tela inicial sem tela branca.
- A tela exibiu o título “Converse com a tradição.”, a proposta de pesquisa, o campo “Pesquisar no acervo”, a indicação de 9 períodos e 27 vozes, o acesso à biblioteca complementar e os 9 cards históricos.
- A navegação principal exibiu o tab Home.
- O teste de entrada pelo navegador alcançou o campo de busca, mas o conteúdo digitado não apareceu na renderização seguinte; é necessário investigar se isso é uma limitação do automator ou um problema de foco/estado no TextInput web.

O teste repetido com foco explícito funcionou: ao digitar “graça”, o campo atualizou e a tela exibiu “6 resultados” e “Pesquisa ativa”, filtrando os cards para os períodos relevantes. O resultado confirmou a busca em tempo real e o botão de limpeza do termo.

A navegação foi validada: o card do período “Pais da Igreja” abriu a rota correspondente e, em seguida, o card de Agostinho de Hipona abriu a conversa. A tela mostrou período, datas, avatar monogramático, botão “Nova”, contexto resumido, quatro perguntas sugeridas, saudação inicial e campo de pergunta fixado na base.

No primeiro teste end-to-end, a chamada direta à OpenAI falhou com erro 401 de credencial. Após a migração para `invokeLLM`, o servidor deixou de usar a chave diretamente; no sandbox, a primeira configuração temporária apontou `BUILT_IN_FORGE_API_URL` para uma URL que já terminava em `/v1`, enquanto o helper acrescenta esse caminho, resultando em 404. O servidor foi reiniciado para o teste local com o sufixo removido. Essa configuração temporária não foi gravada no código nem no pacote.

O diagnóstico bruto mostrou que `gpt-5-mini` recebia o limite `max_tokens: 700`, consumia todo o orçamento em `reasoning_tokens` e retornava `finish_reason: length` sem `message.content`. O proxy respondeu corretamente quando o limite foi omitido; por isso o endpoint agora usa o modelo explícito `gpt-5-mini` sem `maxTokens`. TypeScript, lint e testes voltaram a passar após a remoção do arquivo temporário de diagnóstico.

A validação final foi bem-sucedida: após selecionar “Quais são suas ideias centrais?”, o app mostrou o estado “Consultando as obras e o contexto...” e depois renderizou uma resposta longa contextualizada de Agostinho de Hipona, com aviso explícito de simulação educativa, referências a Confissões, Cidade de Deus e De Trinitate, e distinção entre reconstrução interpretativa e contexto histórico. O fluxo completo de busca, período, teólogo, pergunta e resposta está funcional no Expo web.
