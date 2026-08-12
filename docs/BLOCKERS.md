# BLOCKERS & RISK MITIGATION — RADAR IMOBILIÁRIO AI

Este documento consolida os principais impedimentos técnicos e as estratégias adotadas para mitigá-los durante o desenvolvimento do MVP do Radar Imobiliário AI.

## 1. Scraping e Bloqueio de Rede (CAIXA / Portais Públicos)
- **Impedimento**: Portais públicos como o da CAIXA Econômica e portais de leiloeiros possuem sistemas robustos de mitigação de tráfego robótico (WAF, Cloudflare, CAPTCHAs, limites de requisições). Scraping direto via requisições HTTP comuns costuma ser bloqueado rapidamente.
- **Mitigação**:
  - Implementação de um pipeline de amostragem realista de alta fidelidade e modular, que simula o payload exato retornado por robôs em produção de forma isolada e testável de ponta a ponta.
  - Planejamento de uso de proxies rotativos e navegadores headless (Playwright/Puppeteer) configurados com evasão de detecção (stealth plugins) para a fase de produção.

## 2. Inconsistência e Duplicidade de Dados (Deduplicação)
- **Impedimento**: Imóveis de leilão são frequentemente listados em mais de um portal, ou o mesmo imóvel é re-listado com códigos diferentes, gerando duplicidade no painel. Além disso, as flutuações de lance mínimo precisam ser monitoradas sem sobrescrever o histórico original.
- **Mitigação**:
  - Estabelecimento de um ID canônico robusto combinando chaves naturais exclusivas (como o ID da CAIXA ou hashes baseados na combinação de endereço completo e matrícula).
  - Desenvolvimento de um sistema de histórico de preços (`price_histories`) acionado via gatilhos de backend, registrando as quedas de lance mínimo automaticamente antes do upsert no banco relacional.

## 3. Limitações de Entrega de Notificações
- **Impedimento**: Dependência direta de APIs externas de terceiros (como a do Telegram) para o envio de alertas. Caso a API do Telegram sofra instabilidade ou a credencial não esteja configurada, a pipeline pode falhar de forma silenciosa ou travar o coletor.
- **Mitigação**:
  - Isolamento do pipeline de envio através de um dispatcher desacoplado.
  - Implementação de um mecanismo de entrega resiliente com fallback instantâneo de escrita local em `/tmp/radar_notifications_log.txt`, assegurando que nenhum alerta de oportunidade premium seja perdido.
