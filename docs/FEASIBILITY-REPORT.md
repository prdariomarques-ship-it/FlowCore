# FEASIBILITY REPORT — RADAR IMOBILIÁRIO AI

Relatório de viabilidade de fontes de dados e viabilidade técnica global para o projeto Radar Imobiliário AI.

## 1. Conclusão Geral: GO WITH CONDITIONS
O projeto possui alta viabilidade técnica e mercadológica, sob a condição de utilizarmos barramentos consolidados de alta qualidade (como as planilhas públicas e portais de leilões da CAIXA) em vez de focar no scraping agressivo de leiloeiros privados pequenos com alta variabilidade de interfaces.

## 2. Viabilidade por Fonte de Dados

| Fonte de Dados | Viabilidade Técnica | Classificação | Justificativa |
| :--- | :--- | :--- | :--- |
| **CAIXA Econômica** | **ALTA** | **GREEN** | Interface unificada, planilhas consolidadas e estrutura de dados estável. |
| **Leilões Judiciais** | **MÉDIA** | **YELLOW** | Necessidade de processamento de Diários de Justiça ou APIs de tribunais específicos com alta taxa de indisponibilidade. |
| **Leiloeiros Privados** | **BAIXA / MÉDIA** | **RED** | Mudanças constantes de layout nos sites oficiais e alta presença de bloqueios de rede por Cloudflare. |

## 3. Recomendações de Evolução do MVP
1. **Fase 1 (MVP)**: Ingestão de leilões e licitações extrajudiciais da CAIXA (Executado com Sucesso).
2. **Fase 2 (Evolução)**: Conectar com o serviço oficial de API da CAIXA ou processamento de planilhas locais para evitar bloqueios.
3. **Fase 3 (Alertas)**: Notificação instantânea via Telegram para oportunidades com score superior a 75 (Premium) (Executado com Sucesso).
