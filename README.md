# Radar Imobiliário AI — Console & Analytics MVP

O **Radar Imobiliário AI** é um sistema inteligente de coleta, análise, pontuação e notificação de leilões e oportunidades imobiliárias extrajudiciais e judiciais no Brasil. Com foco inicial na CAIXA Econômica Federal, a plataforma monitora o mercado de leilões ativos de forma 100% autônoma, gerando relatórios de risco, análises de prós e contras e enviando alertas automáticos via Telegram.

---

## 🛠️ Arquitetura do Sistema

A arquitetura segue os princípios estabelecidos pelo protocolo de desenvolvimento ágil do projeto, sendo dividida em módulos independentes e altamente testáveis:

```
├── api/
│   ├── __init__.py
│   └── router.py             # Router REST FastAPI para Web e Mobile
├── data/
│   └── radar.db              # Banco de dados SQLite unificado e idempotente
├── docs/
│   ├── BLOCKERS.md           # Análise de impedimentos e mitigações
│   ├── COMPETITIVE-ANALYSIS.md # Comparação estratégica com concorrentes
│   ├── DECISIONS.md          # Registro de decisões de arquitetura (ADR)
│   ├── FEASIBILITY-REPORT.md # Relatório global de viabilidade de fontes
│   └── SOURCE-MATRIX.md      # Matriz de classificação de adaptadores
├── poc/
│   ├── caixa_poc.py          # POC do coletor ativo da CAIXA
│   ├── dedup_poc.py          # POC do desduplicador e rastreamento de quedas de preço
│   └── notification_poc.py   # POC do pipeline de notificações
├── radar/
│   ├── __init__.py
│   ├── collectors/
│   │   ├── __init__.py
│   │   └── caixa.py          # Coletor ativo e inteligente da CAIXA
│   ├── database/
│   │   ├── __init__.py
│   │   └── db.py             # Gerenciamento de conexões e schema SQLite
│   ├── notifications/
│   │   ├── __init__.py
│   │   └── dispatcher.py     # Despachador de alertas Telegram e fallback
│   └── scoring/
│       ├── __init__.py
│       └── score.py          # Motor de pontuação de oportunidade, risco e dados
├── tests/
│   └── test_radar.py         # Conjunto completo de testes de integração (5/5 PASSING)
├── web/
│   └── index.html            # Console Dashboard Web Premium (Zinc/Slate dark)
└── requirements.txt          # Dependências consolidadas
```

---

## 🌟 Funcionalidades Principais

### 1. Ingestão Ativa CAIXA (`radar/collectors/caixa.py`)
- Coleta ativa de 20 imóveis reais detalhados da CAIXA Econômica Federal.
- Normalização completa de dados cadastrais, financeiros e jurídicos.

### 2. Desduplicador Inteligente (`radar/collectors/caixa.py`)
- Detecção automatizada de duplicidade com base em IDs e hashes naturais.
- **Histórico de Preços (`price_histories`)**: Quando uma flutuação ou queda de preço (lance mínimo) é detectada, o valor antigo é guardado automaticamente para manter a rastreabilidade do desconto.

### 3. Motor de Pontuação (`radar/scoring/score.py`)
- **Opportunity Score (0-100)**: Avalia a atratividade com base na margem de lucro projetada e no status de ocupação.
- **Data Confidence (0-100)**: Mede a completude dos dados cadastrais (CEP, matrícula, matrícula de registro).
- **Risk Score (0-100)**: Mede o risco legal de ocupação, disputas judiciais e dívidas acessórias (condomínio, IPTU).
- **Explainability**: Gera explicações legíveis por humanos sob a forma de listas estruturadas de prós e contras.

### 4. Notificações Telegram (`radar/notifications/dispatcher.py`)
- Dispara alertas no canal do Telegram utilizando templates formatados em Markdown com suporte a deep-links direcionando ao console do Radar.
- **Mecanismo de Fallback**: Caso as chaves do Telegram não estejam configuradas, grava os alertas em `/tmp/radar_notifications_log.txt` para depuração e garantia de entrega.

### 5. Console Dashboard Premium (`web/index.html`)
- Painel web responsivo desenvolvido sob o tema dark **Zinc/Slate** moderno.
- Exibição em tempo real de telemetria do sistema (CPU, memória RAM, capacidade de disco).
- Feed dinâmico de oportunidades de leilão filtráveis por score com expandidores interativos mostrando prós e contras.
- Ações interativas para favoritar oportunidades e acionar o pipeline de ingestão e diagnóstico sob demanda.

---

## 🚀 Como Executar o Projeto

### 1. Instalar as Dependências
Garanta que você possua o Python 3.11+ instalado e execute:
```bash
pip install -r requirements.txt
```

### 2. Rodar os Testes de Integração
Todos os módulos críticos do sistema possuem testes de integração automatizados robustos:
```bash
python -m pytest -v
```

### 3. Executar os Scripts de Demonstração (POCs)
Você pode validar os pipelines isoladamente de maneira rápida:
```bash
# Executar ingestão inicial CAIXA
python -m poc.caixa_poc

# Validar desduplicador e rastreamento de flutuação de preço
python -m poc.dedup_poc

# Validar despacho de alertas com fallback local
python -m poc.notification_poc
```

### 4. Iniciar o Console Web e API Backend

Inicie o servidor de banco de dados e API (FastAPI) em segundo plano:
```bash
PYTHONPATH=. python -m uvicorn api.router:app --host 127.0.0.1 --port 8000
```

Para abrir o painel visual no seu navegador, basta servir a pasta `web/` com qualquer servidor de arquivos estáticos local (como o módulo nativo do Python):
```bash
python -m http.server 3000 --directory web
```
Acesse no seu navegador: `http://localhost:3000`

---

## 🚦 Status de Entrega do Projeto

- [x] **Fase 1: Discovery & Viabilidade** (Competitive Analysis, Source Matrix e Feasibility Report criados) — **DONE**
- [x] **Fase 2: Estrutura do Banco de Dados** (SQLite idempotente, tabelas e constraints configurados) — **DONE**
- [x] **Fase 3: Coletor e Deduplicador** (Normalização da CAIXA, tratamento de quedas de lances no preço histórico) — **DONE**
- [x] **Fase 4: Pipeline de Alertas** (Dispatcher Telegram com template Markdown e log local de fallback) — **DONE**
- [x] **Fase 5: API REST Backend** (Servidor FastAPI unificado, telemetria do SO, rota de diagnóstico on-demand) — **DONE**
- [x] **Fase 6: Console Web Dashboard** (Interface visual premium Zinc/Slate responsiva com filtros dinâmicos) — **DONE**
- [x] **Fase 7: Homologação e Testes** (Testes automatizados e verificação visual com Playwright) — **DONE**
