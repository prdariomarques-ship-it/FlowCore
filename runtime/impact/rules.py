"""First rule set — deterministic macro driver -> asset sensitivity tables (Sprint 23).

Each `DriverRule` covers one of the 3 macro dimensions with real Observer
coverage today (runtime/macro_score/dimension.py's DIMENSIONS — Inflação,
Crescimento, Crédito, Fiscal, Geopolítica still have no data source and
are absent, same discipline as every SCPX stage since Sprint 19).

"Higher inflation" (one of the user's example driver rule sets) has no
direct FlowCore regime dimension — there is no persisted inflation series
anywhere in the stack. It is represented via the "commodities" dimension
(oil+gold) as an inflation-pressure proxy: this mirrors an established,
accepted pattern for this user's own production systems (global
CLAUDE.md's signal-engine uses IRFM11.SA as a proxy for the unavailable
DI futuro series) rather than fabricating a dimension with no backing
data.

Only two real, populated signals are used for hard-column classification
(sector/asset_class come free from yfinance via runtime/portfolio/
asset_provider.py, zero manual tagging required):
  - `sector` (a fixed GICS-like vocabulary yfinance actually returns:
    Technology, Energy, Real Estate, Financial Services, ...).
  - `asset_class` (runtime/portfolio/asset_provider.py's
    _QUOTE_TYPE_TO_ASSET_CLASS vocabulary: equity/etf/mutual_fund/crypto/
    index/currency/future/bond) — only "future" is used here (a
    commodity future contract is unambiguously commodity-class by
    definition, unlike an ETF wrapper, which could hold anything).
  - `country != "United States"` as a deliberately crude Emerging
    Markets proxy for risk_sentiment only (will misclassify developed
    non-US markets like Japan/Germany as EM — a known v1 limitation, not
    silently hidden).

**Architectural boundary (critical, corrected after initial v1 draft):**
this module — and all of runtime/impact/ — must NEVER know about
specific tickers, funds, or products (no "SGOV", no "GLD", no "Tesouro
IPCA+"). It only classifies exposure by *category* (sector, asset class,
country, canonical soft attribute) and, downstream in
runtime/impact/recommendations.py, emits *generic* action keys ("reduce
duration", "increase inflation protection"). Turning a generic action key
into concrete, shelf-specific products (US ETFs, Brazilian renda fixa, a
private bank's shelf, ...) is runtime/product_mapping/'s job, driven
entirely by external, swappable JSON config — never hardcoded here. This
keeps the same Impact/Recommendation Engine reusable across completely
different product shelves without touching this file.

Every rule is defined for the "elevated" regime state only; "depressed"
is always its exact inverse (positive/negative sets swap) rather than a
second hand-maintained table that could silently drift from the first —
see runtime/impact/scenarios.py for where that inversion happens.

Soft-attribute refinement: when a holding has been manually tagged
(runtime.portfolio.attributes.ASSET_ATTRIBUTE_FIELDS) with a *recognized*
level for the dimension's relevant attribute, that tag overrides the
hard-column baseline for that one holding. "média"/"medium" and any
unrecognized free text are never guessed at — they simply fall through
to the hard-column baseline, same insufficient-data-over-fabrication
discipline as every other SCPX engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["DriverRule", "RULES"]


@dataclass(frozen=True)
class DriverRule:
    dimension: str
    driver_when_elevated: str
    driver_when_depressed: str
    reason_when_elevated: str
    reason_when_depressed: str
    negative_sectors_when_elevated: frozenset[str] = frozenset()
    positive_sectors_when_elevated: frozenset[str] = frozenset()
    negative_asset_classes_when_elevated: frozenset[str] = frozenset()
    positive_asset_classes_when_elevated: frozenset[str] = frozenset()
    em_proxy_negative_when_elevated: bool = False
    soft_attribute: str | None = None
    soft_attribute_positive_values: frozenset[str] = field(default_factory=frozenset)
    soft_attribute_negative_values: frozenset[str] = field(default_factory=frozenset)


RULES: dict[str, DriverRule] = {
    "liquidity": DriverRule(
        dimension="liquidity",
        driver_when_elevated="Alta de juros longos (Treasury yields em alta)",
        driver_when_depressed="Queda de juros (Treasury yields em queda)",
        reason_when_elevated=(
            "Juros mais altos pressionam ativos de crescimento e duracao longa "
            "(Tecnologia, REITs, Comunicacao) e favorecem caixa/curto prazo."
        ),
        reason_when_depressed=(
            "Juros em queda favorecem ativos de crescimento e duracao longa e "
            "reduzem a atratividade relativa de caixa/curtissimo prazo."
        ),
        negative_sectors_when_elevated=frozenset(
            {"Technology", "Real Estate", "Communication Services", "Consumer Cyclical"}
        ),
        positive_sectors_when_elevated=frozenset({"Financial Services"}),
        soft_attribute="interest_rate_sensitivity",
        soft_attribute_negative_values=frozenset({"high"}),
        soft_attribute_positive_values=frozenset({"low"}),
    ),
    "commodities": DriverRule(
        dimension="commodities",
        driver_when_elevated="Commodities em alta (proxy de pressao inflacionaria)",
        driver_when_depressed="Commodities em baixa (proxy de desinflacao)",
        reason_when_elevated=(
            "Commodities em alta funcionam como proxy de pressao inflacionaria "
            "- favorece ouro/energia/protecao contra inflacao, pressiona titulos nominais longos."
        ),
        reason_when_depressed=(
            "Commodities em baixa sugerem alivio inflacionario - reduz a "
            "atratividade relativa de ouro/energia/commodities."
        ),
        positive_sectors_when_elevated=frozenset({"Energy", "Basic Materials"}),
        positive_asset_classes_when_elevated=frozenset({"future"}),
        soft_attribute="inflation_protection",
        soft_attribute_positive_values=frozenset({"high"}),
        soft_attribute_negative_values=frozenset({"low"}),
    ),
    "risk_sentiment": DriverRule(
        dimension="risk_sentiment",
        driver_when_elevated="Risk Off (aversao a risco, VIX elevado)",
        driver_when_depressed="Risk On (apetite a risco, VIX deprimido)",
        reason_when_elevated=(
            "Aversao a risco elevada tende a penalizar ativos de maior risco "
            "(small caps, emergentes, alto beta) e favorecer caixa/protecao/dolar."
        ),
        reason_when_depressed=(
            "Apetite a risco elevado favorece ativos de maior beta e penaliza posicoes defensivas/caixa."
        ),
        negative_sectors_when_elevated=frozenset({"Technology", "Consumer Cyclical", "Communication Services"}),
        positive_sectors_when_elevated=frozenset({"Utilities", "Consumer Defensive"}),
        em_proxy_negative_when_elevated=True,
        soft_attribute="risk_attributes",
        soft_attribute_negative_values=frozenset({"high"}),
        soft_attribute_positive_values=frozenset({"low"}),
    ),
}
