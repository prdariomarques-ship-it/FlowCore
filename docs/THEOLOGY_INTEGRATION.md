# Integração de pesquisa teológica

O FlowCore expõe o backend local-first da experiência **Teólogos Chat**. O domínio teológico mantém o catálogo histórico e os prompts de cada pensador, enquanto o FlowCore fornece pesquisa no catálogo, busca em documentos, busca em memórias persistidas, contexto recente e roteamento para o provedor LLM disponível.

## Catálogo histórico

O catálogo sincronizado entre `data/theology_catalog.json` no FlowCore e `data/theologians.ts` no aplicativo contém **12 períodos e 93 teólogos**. A cobertura inclui o Período Apostólico, Padres Apostólicos, Apologistas, Pais da Igreja, Escolástica, Pré-Reforma, Reforma, Pós-Reforma, Avivalistas, Teologia Moderna, Neo-Ortodoxia/Teologia Dialética e Século XX–XXI.

O campo `prompt` permanece interno ao serviço. As rotas públicas de listagem e busca retornam os dados necessários para pesquisa sem expor o prompt histórico completo de cada pensador.

## Rotas teológicas

| Método | Rota | Finalidade |
|---|---|---|
| `GET` | `/api/theology/periods` | Retorna períodos e teólogos sem prompts internos. |
| `GET` | `/api/theology/search?q=graça` | Pesquisa nome, datas, tradição, período e resumo no catálogo local. |
| `POST` | `/api/theology/respond` | Responde usando o prompt histórico, o histórico enviado pelo app e o contexto RAG/memória. |

O corpo de `/api/theology/respond` aceita `theologian_slug`, uma `question` opcional e uma lista `messages` com objetos `{role, content}`. A resposta tem o formato:

```json
{
  "message": "...",
  "model": "...",
  "provider": "...",
  "theologian": {"slug": "...", "name": "..."},
  "source_count": 2,
  "document_count": 1,
  "memory_count": 1,
  "recent_context_used": true
}
```

`source_count` é a soma das fontes usadas; `document_count` indica documentos encontrados; `memory_count` indica memórias encontradas; e `recent_context_used` informa se o contexto recente do acervo/conversa foi acrescentado ao prompt. Quando o acervo não tem correspondência, a resposta pode retornar contagens iguais a zero sem impedir a resposta histórica.

## Conexão com o app Expo

O APK aponta para o servidor **Node/tRPC**, nunca diretamente para o FlowCore. No servidor Node, defina:

```bash
export FLOWCORE_BASE_URL=https://flowcore.example.com
export FLOWCORE_API_TOKEN='token-opcional-apenas-no-servidor'
```

Em desenvolvimento local, `http://127.0.0.1:8765` pode ser usado entre processos na mesma máquina. Para um celular físico, o Node deve ser publicado em um endereço alcançável pelo aparelho, como `http://192.168.1.25:3000` na mesma rede Wi-Fi, ou em uma URL HTTPS. `localhost` e `127.0.0.1` no APK apontam para o próprio telefone.

O token permanece apenas no servidor Node e não deve ser colocado em `EXPO_PUBLIC_*`, no código React Native ou em arquivos versionados. Da mesma forma, `OPENAI_API_KEY` e `OPENROUTER_API_KEY` permanecem exclusivamente nos processos server-side que utilizarem esses provedores.

## RAG e memória local-first

A cada resposta, o FlowCore pesquisa a pergunta em documentos e memórias persistidas, acrescenta contexto recente quando disponível e constrói um prompt específico para o teólogo escolhido. O servidor Node preserva esses sinais no contrato tRPC em camelCase: `sourceCount`, `documentCount`, `memoryCount` e `recentContextUsed`. A tela de conversa exibe esses indicadores abaixo da resposta para que o usuário possa auditar o caminho utilizado.

Para preparar um cenário reproduzível, execute no diretório do FlowCore:

```bash
python3 scripts/seed_theology_demo.py
```

O script insere um documento de demonstração sobre Agostinho e uma memória com as tags `#teologia` e `#agostinho`. A API pode ser verificada com:

```bash
curl -fsS 'http://127.0.0.1:8765/api/search?q=gra%C3%A7a'
curl -fsS 'http://127.0.0.1:8765/api/memories'
```

Depois, configure a URL do Node no painel **Conexão do chat** do APK e pergunte `Como Agostinho entende a graça?`. A linha `FlowCore · ... documentos · ... memórias locais` comprova a utilização do contexto encontrado. Uma linha sem fontes ou sem memória apenas indica que o acervo não encontrou correspondência.

## Inicialização e provedores

A API FastAPI pode ser iniciada com:

```bash
uvicorn api.router:create_app --factory --host 0.0.0.0 --port 8765
```

Para um provedor local, configure `FLOWCORE_OLLAMA` e `FLOWCORE_MODEL`. Para um fallback OpenRouter, configure `OPENROUTER_API_KEY` e, opcionalmente, `OPENROUTER_MODEL` exclusivamente no ambiente do FlowCore. A ausência de um provedor remoto não deve levar chaves para o bundle: o sistema local-first pode continuar usando os adaptadores disponíveis no ambiente.

## Testes

Os testes determinísticos em `tests/test_theology.py` cobrem o catálogo, busca, prompts, inclusão de documentos e memórias e contratos HTTP. O script `scripts/seed_theology_demo.py` é uma ferramenta de demonstração, não uma fixture de produção. A suíte completa do FlowCore deve ser executada com:

```bash
pytest -q
```

A atualização do aplicativo também foi validada com `pnpm check`, `pnpm lint` e `pnpm test`. O teste end-to-end controlado comprovou o encaminhamento Node→FlowCore, a conversão dos campos snake_case para camelCase e a serialização da resposta usada pelo APK.
