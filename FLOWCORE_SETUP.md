# Teólogos Chat + FlowCore

Este documento descreve a configuração da versão mobile atualizada do **Teólogos Chat**. O aplicativo Expo/React Native é o cliente; o servidor Node/tRPC é a única porta acessada pelo APK; e o FlowCore fornece o serviço teológico local-first, com busca em documentos, memória persistida e roteamento para o provedor LLM disponível.

> **Regra de segurança:** nenhuma chave de API deve ser colocada no bundle Expo, em `EXPO_PUBLIC_*`, no `app.config.ts`, no AsyncStorage ou em arquivos versionados. O APK conhece apenas a URL pública do servidor Node.

## Arquitetura de execução

| Componente | Função | Onde configurar segredos |
|---|---|---|
| APK Teólogos Chat | Pesquisa, seleção do teólogo e interface de conversa | Não recebe chaves; recebe somente a URL pública do Node pelo painel **Conexão do chat** |
| Servidor Node/tRPC | Valida a entrada, encaminha para FlowCore e mantém fallback LLM | `FLOWCORE_BASE_URL`, `FLOWCORE_API_TOKEN` e credenciais do helper LLM ficam somente no servidor |
| FlowCore/FastAPI | Catálogo, contexto histórico, RAG, memórias e roteamento local-first | `FLOWCORE_OLLAMA`, `FLOWCORE_MODEL`, `OPENROUTER_API_KEY` ou outro provedor configurado no servidor FlowCore |

O APK não deve apontar diretamente para o FlowCore. Ele deve apontar para o **Node**, por exemplo `https://teologia.example.com` ou `http://192.168.1.25:3000`. O Node, por sua vez, usa `FLOWCORE_BASE_URL` para acessar o FlowCore.

## 1. Configurar o FlowCore

Na máquina que executará a API Python, instale as dependências e inicie a aplicação FastAPI usando a função de fábrica existente:

```bash
cd /caminho/FlowCore-main-integration
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-api.txt

# Exemplo de execução local
uvicorn api.router:create_app --factory --host 0.0.0.0 --port 8765
```

A instalação local-first pode usar Ollama. Nesse caso, configure o endereço e o modelo disponíveis na máquina:

```bash
export FLOWCORE_OLLAMA=http://127.0.0.1:11434
export FLOWCORE_MODEL=nome-do-modelo-local
```

Se o ambiente usar o provedor OpenRouter como fallback ou como provedor remoto, a chave deve existir apenas no processo do FlowCore:

```bash
export OPENROUTER_API_KEY='chave-do-servidor'
export OPENROUTER_MODEL='modelo-do-provedor'
```

Quando houver um provedor OpenAI ou compatível configurado especificamente no ambiente de execução, `OPENAI_API_KEY` também deve permanecer apenas no servidor. A integração fornecida pelo aplicativo não lê essa chave no React Native e não a envia pelo tRPC.

Verifique a API Python:

```bash
curl -fsS http://127.0.0.1:8765/api/health
curl -fsS 'http://127.0.0.1:8765/api/theology/periods'
curl -fsS 'http://127.0.0.1:8765/api/theology/search?q=gra%C3%A7a'
```

## 2. Configurar o servidor Node/tRPC

Na máquina que será alcançada pelo APK, instale as dependências e defina a URL do FlowCore. O token é opcional e só deve ser usado quando o gateway do FlowCore exigir autenticação:

```bash
cd /caminho/FlowCore-teologos
pnpm install

export FLOWCORE_BASE_URL=http://127.0.0.1:8765
export FLOWCORE_API_TOKEN='token-apenas-do-servidor'   # opcional
pnpm dev:server
```

Para desenvolvimento em que o celular e o computador estão na mesma rede Wi-Fi, o Node precisa escutar em uma interface alcançável e o APK precisa usar o IP do computador, não `127.0.0.1`:

```text
URL a salvar no APK: http://192.168.1.25:3000
```

O endereço `127.0.0.1`, `localhost` ou uma URL vazia no APK aponta para o próprio aparelho Android. Esse foi o motivo principal de a versão anterior permitir digitar uma mensagem, mas não receber resposta do servidor. Em produção, prefira HTTPS e um domínio ou túnel estável.

O servidor expõe a verificação:

```bash
curl -fsS http://127.0.0.1:3000/api/health
```

Se a porta 3000 estiver ocupada, o servidor de desenvolvimento pode escolher a próxima porta disponível; nesse caso, salve no APK a porta realmente exibida no log.

## 3. Configurar e testar o APK

Abra a tela inicial do aplicativo e expanda **Conexão do chat**. Informe a URL do **servidor Node**, toque em **Salvar** e depois em **Testar**. O resultado esperado é uma mensagem de servidor conectado. A URL é persistida localmente no dispositivo, e o cliente tRPC consulta essa configuração a cada requisição.

Em seguida, abra qualquer período, selecione um teólogo e envie uma pergunta. O estado de carregamento deve aparecer como **“Consultando as obras e o contexto…”**. Depois da resposta, a tela pode exibir uma linha semelhante a `FlowCore · 2 documentos · 1 memória local · contexto recente`. Esses indicadores são retornados pelo FlowCore e permitem distinguir uma resposta realmente enriquecida de uma resposta do fallback LLM.

Se o chat falhar, a mensagem agora informa o erro do servidor. Volte à tela inicial, confirme a URL, toque em **Testar** e verifique se o celular consegue alcançar o computador na mesma rede. Também confirme o firewall, a porta escolhida e se o Node está configurado com `FLOWCORE_BASE_URL`.

## 4. Testar RAG e memória local-first com dados controlados

Para criar uma fonte teológica e uma memória de demonstração no banco local do FlowCore, execute no servidor FlowCore:

```bash
cd /caminho/FlowCore-main-integration
source .venv/bin/activate
python3 scripts/seed_theology_demo.py
```

Esse script insere uma fonte marcada como `theology-demo` e uma memória com os termos `graça` e `Agostinho`. Ele não contém chaves e deve ser usado somente em ambiente de teste. Depois, confirme os registros:

```bash
curl -fsS 'http://127.0.0.1:8765/api/search?q=gra%C3%A7a'
curl -fsS 'http://127.0.0.1:8765/api/memories'
```

Com o Node e o APK configurados, envie exatamente uma pergunta como **“Como Agostinho entende a graça?”**. A resposta deve mostrar pelo menos um documento ou uma memória local, conforme os dados e o mecanismo de busca disponíveis. Para testar o contexto de conversa, faça uma segunda pergunta relacionada sem repetir todos os termos; o histórico recente enviado pelo aplicativo deve ser considerado, e a indicação `contexto recente` aparecerá quando o FlowCore marcar essa utilização.

Uma resposta sem documentos ou memórias não significa necessariamente falha: um acervo vazio ou uma pergunta sem correspondência legítima resulta em `0` fontes, preservando a resposta histórica do teólogo. Para comprovar o caminho FlowCore, observe a linha de indicadores na resposta; o fallback direto do Node não apresenta esses sinais.

## 5. Contratos e chaves

| Variável | Processo | Obrigatória | Observação |
|---|---|---:|---|
| `FLOWCORE_BASE_URL` | Node | Para RAG/memória | URL interna do FlowCore, sem barra final |
| `FLOWCORE_API_TOKEN` | Node | Não | Token opcional para o gateway FlowCore |
| `FLOWCORE_OLLAMA` | FlowCore | Não | Endereço explícito do Ollama local |
| `FLOWCORE_MODEL` | FlowCore | Não | Modelo local escolhido |
| `OPENROUTER_API_KEY` | FlowCore | Conforme provedor | Nunca vai para o APK |
| `OPENAI_API_KEY` | Servidor compatível | Conforme provedor | Nunca vai para o APK; a implementação padrão usa helper server-side |
| `EXPO_PUBLIC_API_BASE_URL` | Build Expo | Não | Apenas URL pública opcional, nunca segredo |

O endpoint teológico do FlowCore recebe `theologian_slug` e `messages` e devolve `message`, `model`, `provider`, `theologian`, `source_count`, `document_count`, `memory_count` e `recent_context_used`. O Node converte os campos para o contrato camelCase usado pelo aplicativo.

## 6. Validação realizada

A atualização foi validada com TypeScript, lint, testes do catálogo, testes teológicos do FlowCore e a suíte completa do backend. Também foi executado um teste end-to-end controlado em que o Node encaminhou uma mutation tRPC para um stub compatível com FlowCore e devolveu corretamente mensagem, documentos, memória e contexto recente. O resultado detalhado está em `theology-validation-evidence.md`.

## 7. Publicação

O APK de produção deve ser gerado novamente depois desta correção. O perfil `preview` do EAS gera um APK de distribuição interna para instalação direta, sem publicar na Google Play. O código atualizado permanece sem credenciais e deve ser configurado com segredos no ambiente de execução do servidor.
