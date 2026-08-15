# Integração de pesquisa teológica

O FlowCore expõe o backend local-first da experiência Teólogos Chat. O domínio teológico mantém o catálogo histórico e os prompts de cada pensador, enquanto o FlowCore fornece busca em documentos, busca em memórias e roteamento para o provedor LLM configurado.

## Rotas

| Método | Rota | Finalidade |
|---|---|---|
| `GET` | `/api/theology/periods` | Retorna os períodos e teólogos do catálogo, sem expor prompts internos. |
| `GET` | `/api/theology/search?q=graça` | Pesquisa nome, datas, tradição, período e resumo no catálogo local. |
| `POST` | `/api/theology/respond` | Responde uma pergunta usando o prompt histórico, o histórico enviado pelo app e o contexto RAG/memória do FlowCore. |

O corpo de `/api/theology/respond` aceita `theologian_slug`, uma `question` opcional e uma lista `messages` com objetos `{role, content}`. A resposta contém `message`, `model`, `provider`, `theologian` e `source_count`.

## Conexão do app Expo

No servidor Node do app, defina `FLOWCORE_BASE_URL` apontando para a URL do FlowCore. Se a API estiver protegida por um gateway, defina também `FLOWCORE_API_TOKEN`; o token permanece apenas no servidor Node e não é enviado ao bundle Expo. Quando `FLOWCORE_BASE_URL` não estiver definido, o app mantém o fallback local para desenvolvimento.

```bash
FLOWCORE_BASE_URL=http://127.0.0.1:8765 pnpm dev
```

Em produção, use uma URL HTTPS e configure o segredo no ambiente de execução do servidor. Não coloque `FLOWCORE_API_TOKEN` em `EXPO_PUBLIC_*` nem em arquivos versionados.

## RAG e memória

A cada resposta, o FlowCore pesquisa a pergunta nos documentos e nas memórias persistidas, acrescenta um contexto recente do acervo e constrói um prompt específico para o teólogo selecionado. A ausência de documentos não bloqueia a resposta: nesse caso, o prompt informa que não há fonte local relevante e a API retorna `source_count: 0`.

O catálogo está em `data/theology_catalog.json` e foi exportado da branch `teologos-chat` para evitar duplicação manual entre TypeScript e Python. O carregador Python não expõe o campo `prompt` nas rotas de listagem e busca.

## Execução e validação

Na raiz do FlowCore, instale `requirements-api.txt` e execute o servidor FastAPI conforme o procedimento padrão do projeto. Os testes determinísticos estão em `tests/test_theology.py`. Eles cobrem contagem do catálogo, pesquisa, inclusão de documentos e memórias no prompt e os contratos HTTP das três rotas.
