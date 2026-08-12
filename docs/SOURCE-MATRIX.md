# SOURCE MATRIX — RADAR IMOBILIÁRIO AI

Matriz de classificação de fontes e adaptadores do sistema.

## 1. Classificação das Fontes de Dados

### 🟢 GREEN (Alta Viabilidade)
- **CAIXA Econômica Federal**: Principal fonte extrajudicial. Possui leilões, licitações fechadas, vendas diretas online. Facilmente catalogável e altamente estável.

### 🟡 YELLOW (Média Viabilidade)
- **Mega Leilões / Zuk**: Leiloeiros consolidados com APIs de divulgação parciais ou layouts consistentes de fácil extração de dados.

### 🔴 RED (Baixa Viabilidade)
- **Pequenos Leiloeiros Regionais**: Layouts inconsistentes, alta variabilidade de PDFs de editais, risco de quebra constante de scrapers.

## 2. Status dos Adaptadores de Ingestão

- **Adaptador CAIXA (Extrajudicial)**: 🟢 **ATIVO & FUNCIONAL** (Módulo `radar.collectors.caixa`).
- **Pipeline de Pontuação**: 🟢 **ATIVO & FUNCIONAL** (Módulo `radar.scoring.score`).
- **Pipeline de Notificação (Telegram)**: 🟢 **ATIVO & FUNCIONAL** (Módulo `radar.notifications.dispatcher`).
