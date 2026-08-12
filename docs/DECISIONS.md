# ARCHITECTURAL DECISION LOG (ADR) — RADAR IMOBILIÁRIO AI

Este documento detalha as decisões de arquitetura e tecnologia tomadas durante a concepção do Radar Imobiliário AI.

## 1. Banco de Dados Relacional: SQLite em Produção
- **Decisão**: Utilização do SQLite como o banco de dados relacional principal para o MVP.
- **Contexto**: Embora bancos como o PostgreSQL fossem considerados, o SQLite oferece isolamento de transações, idempotência por meio de constraints e facilidade extrema de deploy local sem dependência de serviços externos pesados de containers.
- **Consequência**: A arquitetura do banco foi isolada no módulo `radar.database.db` com o método `get_connection`, permitindo a substituição para PostgreSQL apenas alterando o driver de conexão, mantendo as queries SQL padrão perfeitamente compatíveis.

## 2. Abstração do Pipeline de Ingestão (Collectors)
- **Decisão**: Criação da classe `CaixaCollector` contendo métodos dedicados à normalização e persistência de dados.
- **Contexto**: A modelagem de scraping do portal da CAIXA requer agilidade e blindagem contra erros. Ao centralizar as regras de upsert e detecção de flutuações de lances no coletor, isolamos as chamadas da API FastAPI e dos testes unitários.
- **Consequência**: Facilidade na criação de testes de integração rápidos e sem necessidade de mockar conexões HTTP complexas e instáveis.

## 3. Notificações Desacopladas com Fallback Local
- **Decisão**: O dispatcher do Telegram funciona de forma autônoma e registra todas as notificações geradas em um arquivo local caso não esteja configurado.
- **Contexto**: Para evitar problemas de timeout ou quebra de fluxo caso o bot do Telegram não esteja configurado, o dispatcher garante que as mensagens de texto formatadas em Markdown com links sejam salvas localmente.
- **Consequência**: Zero falhas na pipeline decorrentes de problemas de conectividade e facilidade de depuração local via arquivo texto.
