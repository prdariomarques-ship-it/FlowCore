# Teólogos Chat + FlowCore

Esta é a atualização do aplicativo Expo/React Native Teólogos Chat já existente. A interface permanece a mesma, mas as conversas passam a ser encaminhadas ao backend teológico do FlowCore quando `FLOWCORE_BASE_URL` está configurado no servidor Node do app.

## Execução local

Na raiz do projeto, instale as dependências e inicie o app com a URL do FlowCore:

```bash
pnpm install
FLOWCORE_BASE_URL=http://127.0.0.1:8765 pnpm dev
```

Em produção, use uma URL HTTPS para o FlowCore. Se houver autenticação entre os serviços, configure `FLOWCORE_API_TOKEN` somente no ambiente do servidor Node. Não use essas variáveis com o prefixo `EXPO_PUBLIC_`, porque elas não devem entrar no bundle do aplicativo.

Quando `FLOWCORE_BASE_URL` não estiver definido, o resolver mantém um fallback local para desenvolvimento isolado. Quando estiver definido, a resposta passa pelo endpoint `/api/theology/respond` e pode retornar `sourceCount`, que a tela exibe como a quantidade de fontes locais encontradas.

## Validação

A atualização foi verificada com TypeScript, lint, testes automatizados e uma chamada HTTP encadeada pelo resolver tRPC até o FlowCore. O backend correspondente está na branch `manus/teologia-rag` do repositório FlowCore.
