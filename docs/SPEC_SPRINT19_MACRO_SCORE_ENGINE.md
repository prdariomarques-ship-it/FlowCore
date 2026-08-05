# Sprint 19 — SCPX Event Store + Macro Score Engine v1

Author: Claude Code (architecture role). Implementer: Jules.
Depends on: Sprint 18 (`runtime/observers/`, commit `782659c`), already merged.

## Contexto — o que já existe (não repetir)

O `runtime/observers/` (Sprint 18) já entrega a camada "Observer" completa:
`Observer` ABC, `MarketEvent` canônico (`id, timestamp, source, category,
symbol, event, severity, confidence, payload, metadata`), `ObserverRegistry`,
`ObserverScheduler` (`run_once()`/`run_forever()`), 5 observers via yfinance
(treasury, dollar, vix, oil, gold), exposto em `/api/observer/*`,
`flowcore.py observer <registry|events|health|watch>`, e 4 tools MCP.

**A camada de normalização do diagrama do usuário já está satisfeita por
construção**: todo Observer só consegue emitir `MarketEvent` (contrato do
ABC), então não existe vazamento de schema externo rio abaixo. Não crie uma
camada "Normalizer" separada — seria uma abstração sem consumidor, contra
`FLOWCORE_CONSTITUTION.md` ("Avoid abstractions without consumers").

**O que NÃO existe hoje, e é o maior risco arquitetural do projeto:**
o estado de "último valor" de cada Observer vive só em memória, por
processo, e é perdido a cada restart. Não existe histórico persistido em
lugar nenhum. Isso significa que, hoje, seria literalmente impossível
construir um Macro Score Engine real: não há dado para calcular tendência,
média móvel, z-score ou qualquer coisa que dependa de "o que aconteceu nas
últimas semanas". Qualquer sprint que pule direto para "scoring" sem
resolver isso primeiro estaria construindo sobre uma fundação vazia.

## Objetivo

Fechar essa lacuna e entregar o primeiro estágio real de interpretação do
pipeline SCPX:

```
Observer Layer → MarketEvent → [Normalização: já satisfeita] →
Event Store (novo) → Macro Score Engine v1 (novo)
```

Ao final da sprint, o FlowCore deve conseguir responder, de forma
determinística e explicável: "como estão as condições macro observáveis
hoje, comparadas com o histórico recente, em cada dimensão que já temos
dado real?" — sem qualquer interpretação de LLM, sem recomendação, sem
portfólio.

## Escopo

### 1. Event Store (`storage/event_repo.py`, novo)

Mesma forma de `storage/flow_repo.py` (`FlowRepository`): classe async,
`aiosqlite`, mesmo banco via `storage.database.get_db_path()`,
`ensure_tables()` idempotente. **Fica no tier core** (não depende de
yfinance nem de nada de `runtime/observers/` — recebe `dict`, não
`MarketEvent`, para não inverter a direção de dependência
storage→runtime).

```python
class EventRepository:
    async def ensure_tables(self) -> None: ...
    async def insert_event(self, event: dict) -> None: ...
    async def list_events(
        self, source: str | None = None, since: str | None = None, limit: int | None = None
    ) -> list[dict]: ...
```

Schema:
```sql
CREATE TABLE IF NOT EXISTS market_events (
    id TEXT PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    source TEXT NOT NULL,
    category TEXT NOT NULL,
    symbol TEXT NOT NULL,
    event TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence REAL NOT NULL,
    payload TEXT NOT NULL,   -- JSON
    metadata TEXT NOT NULL,  -- JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_market_events_source_ts ON market_events(source, timestamp);
```

Registrar em `storage/__init__.py` junto com os outros repos.

### 2. Persistência automática no scheduler (`runtime/observers/scheduler.py`, modificar)

`ObserverScheduler` ganha uma dependência opcional de `EventRepository`
(injetada no construtor, `None` por padrão para não quebrar os testes/uso
atual). Quando presente, **todo** `MarketEvent` produzido por
`run_once()` — não importa se disparado por API, CLI, MCP ou pelo loop
`run_forever()` — é persistido antes de retornar. Isso garante que
qualquer chamada, mesmo ad hoc, contribui para o histórico.

`service.py`: o `ObserverScheduler` singleton passa a ser construído com
um `EventRepository()` real (mesmo padrão de `_flow_repo`/`_doc_repo`).

### 3. Coleta contínua (operacional, não código novo)

`flowcore.py observer watch --interval N` já existe (Sprint 18) e, com a
mudança acima, já persiste a cada ciclo. Documentar (README ou comentário
em `.env.example`) a recomendação de rodar como **systemd user service**,
exatamente como `spcx-monitor`/`signal-engine`/`renda-fixa-monitor` já
rodam hoje (ver `CLAUDE.md` global do usuário) — reaproveita um padrão
operacional já validado em vez de inventar um novo (ex: integrar no
`FlowCoreDaemon`, que é uma feature separada e já entregue; não mexer
nela nesta sprint).

### 4. Macro Score Engine v1 (`runtime/macro_score/`, novo pacote)

**Fica inteiramente no tier core** — só lê histórico já persistido, nunca
toca rede/yfinance diretamente. Isso é uma propriedade arquitetural
importante: o Macro Score Engine pode rodar (e ser testado) mesmo sem
`requirements-api.txt` instalado.

```
runtime/macro_score/
    __init__.py
    dimension.py    # dimensão -> lista de sources que a alimentam
    score.py         # DimensionScore dataclass
    engine.py          # MacroScoreEngine.compute_scores()
```

**`dimension.py`** — mapeamento explícito, mirror do padrão
`_default_observers()` (lista explícita, sem auto-discovery):

```python
DIMENSIONS = {
    "commodities": ["oil", "gold"],
    "liquidity": ["treasury", "dollar"],
    "risk_sentiment": ["vix"],
}
```

Só as 3 dimensões com cobertura real de dado. As dimensões que o usuário
listou originalmente (Inflação, Crescimento, Crédito, Fiscal, Geopolítica)
**não têm nenhum Observer alimentando-as hoje** — ficam de fora
explicitamente (não fabricar score de dimensão sem dado real). Adicionar
uma nova dimensão, ou mover um source entre dimensões, é uma mudança de
uma linha aqui — nenhum outro arquivo muda (Open/Closed, mesmo padrão do
registry de Observers).

**`score.py`**:
```python
@dataclass
class DimensionScore:
    dimension: str
    status: str  # "scored" | "insufficient_data"
    score: float | None          # média dos z-scores dos sources, None se insufficient_data
    window_days: int
    z_scores: dict[str, float]   # por source, para explicabilidade
    sample_counts: dict[str, int]
    computed_at: str
```

**`engine.py`**:
```python
class MacroScoreEngine:
    def __init__(self, event_repo: EventRepository, window_days: int = 30, min_samples: int = 5): ...
    async def compute_score(self, dimension: str) -> DimensionScore: ...
    async def compute_all(self) -> list[DimensionScore]: ...
```

Cálculo, por source dentro de uma dimensão:
1. `list_events(source=X, since=now-window_days)` do `EventRepository`.
2. Extrai `payload["value"]` de cada evento.
3. Se `len(values) < min_samples` → esse source não entra na média (fica
   registrado em `sample_counts` com sua contagem real, mas sem z-score).
4. `z = (último_valor - média_janela) / desvio_padrão_janela` (desvio 0
   → z = 0, não divide por zero).
5. `DimensionScore.score` = média dos `z` disponíveis. Se **nenhum**
   source da dimensão tem amostras suficientes → `status =
   "insufficient_data"`, `score = None` (nunca inventar um número).

Nada de LLM, nada de threshold que vire "compre/venda" — isso é
interpretação, proibida nesta camada (`FLOWCORE_CONSTITUTION.md`, "AI
Philosophy": "Never delegate deterministic business logic to an LLM" e,
simetricamente aqui, o próprio Macro Score Engine não decide nada, só
mede e explica).

### 5. `service.py` / `api/router.py` / `flowcore.py` / `mcp_server.py`

Mesmo padrão de todas as integrações desta sprint:

- `service.py`: `macro_score_dimensions()` (lista estática, sem I/O),
  `macro_score_compute(dimension)`, `macro_score_compute_all()`.
- `api/router.py`:
  `GET /api/macro-score/dimensions` — lista de dimensões + sources mapeados
  `GET /api/macro-score/scores` — todas as dimensões
  `GET /api/macro-score/scores/{dimension}` — uma dimensão; 404 se desconhecida
- `flowcore.py`: `macro-score <dimensions|scores|scores <dimension>>`.
- `mcp_server.py`: `flowcore_macro_score_dimensions/scores/score`.

## Fora do escopo (explícito)

- Regime Engine, Portfolio Impact Engine, Recommendation Engine, Alert
  Engine — fases seguintes do pipeline, dependem do que esta sprint
  entrega mas não são construídas aqui.
- Qualquer modelo de portfólio/holdings do usuário — necessário antes do
  Portfolio Impact Engine, não antes disso.
- Novas dimensões sem Observer real (Inflação, Crescimento, Crédito,
  Fiscal, Geopolítica) — aguardam novos Observers em sprints futuras.
- Pesos diferentes por source dentro de uma dimensão (v1 usa média
  simples) — refinável depois sem quebrar o contrato da API.
- Integração do scheduler com `FlowCoreDaemon` — o `observer watch` já
  resolve coleta contínua via o padrão systemd que o usuário já usa.
- Qualquer UI nova (segue o corte já estabelecido: Claude Code define
  arquitetura, Jules cuida de UI/frontend quando houver frontend a fazer
  — aqui ainda é só backend).

## Arquitetura

```
ObserverScheduler.run_once()
    → [Observer.observe() por source] → MarketEvent
    → EventRepository.insert_event() (novo hook, opcional/injetado)
    → retorna eventos (comportamento existente inalterado)

MacroScoreEngine.compute_score(dimension)
    → EventRepository.list_events(source, since=window) por source da dimensão
    → z-score por source → média → DimensionScore
```

Direção de dependência: `runtime/macro_score/` depende de `storage/`
(EventRepository) e de nada mais — não importa `runtime/observers/`
diretamente (só consome o que já está persistido como `dict`, não
`MarketEvent`). Isso mantém a mesma separação de camadas que
`FLOWCORE_CONSTITUTION.md` pede ("Storage owns persistence", "Runtime
communicates with providers") e é o que permite o Macro Score Engine
rodar sem `requirements-api.txt`.

## Responsabilidades

- **Claude Code**: já entregou esta especificação; revisão de arquitetura
  do PR resultante antes de merge (conferir que a separação de camadas
  acima foi respeitada, que nenhuma dimensão foi "inventada" sem dado
  real, e que não houve LLM/threshold de decisão infiltrado no engine).
- **Jules**: implementação completa (Event Store, hook no scheduler,
  Macro Score Engine, as 4 interfaces, testes, verificação, commits
  incrementais por item do escopo acima — não um commit monolítico).

## Testes

- `tests/test_event_repo.py` (novo, tier core — sem `importorskip`): CRUD
  básico, `list_events` filtrando por `source`/`since`/`limit`, ordenação,
  tabela idempotente (`ensure_tables()` chamável repetidas vezes).
- `tests/observers/test_scheduler.py` (estender): `run_once()` com um
  `EventRepository` real (SQLite em `tmp_path`) persiste os eventos
  produzidos; sem repositório injetado, comportamento idêntico ao de hoje
  (backward compatible — testar explicitamente).
- `tests/macro_score/test_engine.py` (novo, tier core): histórico
  sintético via `EventRepository` real em `tmp_path` —
  - dimensão com amostras suficientes em todos os sources → score
    determinístico, `z_scores` corretos (calcular à mão o esperado no
    teste).
  - dimensão com um source sem dado suficiente → esse source ausente de
    `z_scores`, mas presente em `sample_counts` com a contagem real.
  - dimensão sem NENHUM source com dado suficiente →
    `status="insufficient_data"`, `score=None`.
  - desvio-padrão zero (todos os valores iguais) → z=0, não
    `ZeroDivisionError`.
  - dimensão desconhecida → erro claro (mesma convenção de
    `ObserverRegistry.get()` para observer desconhecido).
- `tests/test_api.py`: `TestMacroScoreEndpoints`, mesmo padrão de
  `TestObserverEndpoints` (mock em `service.macro_score_*`).
- Rodar contra venv core-only (`requirements-core.txt` apenas) —
  `runtime/macro_score/` e `storage/event_repo.py` devem passar sem
  nenhum skip, diferente dos testes de `runtime/observers/`.

## Critérios de aceitação

1. Eventos sobrevivem a um restart do processo (teste manual: rodar
   `observer events`, reiniciar o processo, consultar o histórico via
   novo endpoint/CLI e confirmar que os dados persistiram).
2. `flowcore.py observer watch` rodando por alguns ciclos produz linhas
   consultáveis em `market_events`.
3. Com menos de `min_samples` eventos para uma dimensão, a API retorna
   `status="insufficient_data"` e `score=None` — nunca um número
   fabricado.
4. Com histórico suficiente, o mesmo histórico produz sempre o mesmo
   score (determinístico, sem aleatoriedade, sem chamada a Ollama/
   Anthropic/qualquer LLM).
5. Toda resposta de score inclui `z_scores` e `sample_counts` — dá pra
   explicar o número sem abrir código.
6. `runtime/macro_score/` e `storage/event_repo.py` importam e passam nos
   testes num venv só com `requirements-core.txt`.
7. As 4 interfaces (CLI, API, MCP, testes) expõem dimensions/scores/score
   por dimensão, seguindo exatamente os nomes de rota/comando definidos
   acima.
8. CI verde (lint + core tests + api tests).

## Validação

- `ruff check .` / `ruff format --check .`.
- `pytest -q` completo (ambiente normal) — não pode regredir os 350
  testes já existentes.
- Venv core-only (`python3 -m venv` + `pip install -r
  requirements-core.txt pytest`) — `tests/test_event_repo.py` e
  `tests/macro_score/` devem passar sem skip.
- Verificação ao vivo: rodar `flowcore.py observer watch --interval 5`
  por ~1 minuto (histórico real, ainda que pequeno), depois chamar
  `/api/macro-score/scores` e conferir que pelo menos `risk_sentiment`
  (alimentada só por `vix`, então precisa de menos amostras cruzadas)
  aparece com `status` coerente dado o tamanho real do histórico
  coletado.
- CLI smoke test: `macro-score dimensions`, `macro-score scores`,
  `macro-score scores risk_sentiment`.
- MCP smoke test: as 3 tools nas duas situações (com e sem histórico
  suficiente).
- `gh run watch --exit-status` até CI verde.

## Compatibilidade

- Nenhuma rota/comando/tool do Sprint 18 muda de nome ou de contrato.
  `ObserverScheduler(registry)` sem `event_repo` continua funcionando
  exatamente como hoje (parâmetro novo é opcional, testar isso
  explicitamente).
- Mesmo arquivo de banco (`data/flowcore.db`) que `FlowRepository`/
  `DocumentRepository`/`MemoryRepository` já usam — uma tabela nova, sem
  alterar as existentes.
- Nenhuma dependência nova em `requirements-api.txt` ou
  `requirements-core.txt` (aiosqlite já é core).

## Estratégia de evolução

- Fase 3 (Regime Engine, sprint futura) consome `MacroScoreEngine.
  compute_all()` diretamente — não precisa de nada além do que esta
  sprint expõe.
- Novas dimensões (Inflação, Crescimento, Crédito, Fiscal, Geopolítica)
  entram como: (1) um novo Observer alimentando um novo `source`, (2) uma
  linha nova em `DIMENSIONS`. Nenhuma outra mudança.
- Pesos por source, janelas diferentes por dimensão, ou um método de
  score mais sofisticado que z-score médio — tudo isso é um `v2` do
  `MacroScoreEngine` que troca a implementação interna sem quebrar
  `DimensionScore` nem as rotas.
- Se `runtime/observers/` e `runtime/macro_score/` ganharem uma terceira
  camada irmã (Regime Engine) no futuro próximo, vale considerar
  reagrupar as três sob um único `runtime/scpx/` — não fazer essa
  reorganização agora (baixo valor, alto blast radius em código recém-
  entregue).

## Não-negociáveis (repetição da Constituição, para não passar batido)

- Nunca duplicar lógica — reusar `FlowRepository` como template, não
  reinventar o padrão de repositório.
- Sem lógica de negócio dentro de rotas/CLI/MCP — tudo passa por
  `service.py`.
- Sem abstração sem consumidor — não construir Normalizer separado, não
  pontuar dimensão sem Observer real.
- Todo score explicável — `z_scores`/`sample_counts` sempre presentes.
- LLM nunca decide nada nesta camada.
- Commits pequenos e lógicos, push após cada item estável do escopo,
  nunca acumular trabalho incompleto.
