# Teólogos Chat — Guia de migração

Este pacote contém o código-fonte do aplicativo mobile React + Expo, o servidor tRPC, o catálogo de períodos e teólogos, os system prompts, os assets de branding, as configurações do Expo/EAS e os testes.

## Requisitos

Use Node.js compatível com o Expo SDK 54 e pnpm. Depois de extrair o pacote, execute `pnpm install` para restaurar as dependências a partir de `package.json` e `pnpm-lock.yaml`.

## Variáveis de ambiente

Configure as variáveis no ambiente de destino. A chave `OPENAI_API_KEY` deve existir somente no servidor e nunca deve ser colocada no código do aplicativo ou versionada no repositório. O pacote exportado não contém tokens Expo, arquivos `.env`, credenciais ou o arquivo interno de configuração do ambiente Manus.

## Execução local

Use `pnpm dev` para iniciar o servidor e o Metro/Expo web. Para validar o projeto, execute `pnpm check`, `pnpm lint` e `pnpm test`.

## Build Expo/EAS

O `app.config.ts` está vinculado ao owner Expo `DMN0712`. O `eas.json` fornece os perfis `development`, `preview` e `production`. Faça login na conta Expo correta e forneça o token diretamente ao fluxo EAS; não inclua o token em arquivos do projeto.

## Estrutura principal

- `app/`: telas e rotas Expo Router.
- `components/`, `hooks/`, `lib/`: componentes e utilitários compartilhados.
- `data/theologians.ts`: catálogo dos períodos, teólogos e system prompts.
- `server/`: endpoint tRPC e integração server-side com OpenAI.
- `assets/images/`: ícones e assets do aplicativo.
- `tests/`: testes determinísticos do catálogo.
- `app.config.ts` e `eas.json`: configuração Expo/EAS.
