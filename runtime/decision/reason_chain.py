"""Reason Chain (Sprint 24, Layer 5 component).

Every decision explains itself as an ordered list of plain-language
steps, answering the Sprint 24 spec's 8 required questions (what
happened / why / why it matters / why this portfolio / why now / what
happens if nothing is done / expected benefit / why this confidence).
Built entirely from data already computed by upstream engines (Regime,
Portfolio Impact, Recommendation, Concentration) -- no LLM, no new
interpretation invented here, just narration of facts already computed.
"""

from __future__ import annotations

__all__ = ["build_for_driver", "build_for_concentration"]

_DIMENSION_LABEL = {
    "liquidity": "Juros / Treasury yields",
    "commodities": "Commodities / proxy de inflacao",
    "risk_sentiment": "Sentimento de risco (VIX)",
}


def build_for_driver(driver, recommendation) -> list[str]:
    """driver: runtime.impact.models.DriverImpact. recommendation:
    runtime.impact.models.Recommendation, already matched to this
    driver via its `dimension` field."""
    label = _DIMENSION_LABEL.get(driver.dimension, driver.dimension)
    score_str = f" (score={driver.regime_score:+.2f})" if driver.regime_score is not None else ""
    chain = [f"O que aconteceu: {label} esta em regime '{driver.regime}'{score_str}."]
    chain.append(f"Por que: {driver.reason}")

    if driver.buckets:
        top = driver.buckets[0]
        chain.append(f"Por que este portfolio: {top.label} representa {top.weight_pct:.1f}% do valor do portfolio.")
    else:
        chain.append("Por que este portfolio: nenhuma holding classificada foi diretamente afetada.")

    chain.append(
        f"Por que importa: {driver.exposed_weight_pct:.1f}% do portfolio esta classificado com "
        f"impacto esperado '{driver.expected_impact}'."
    )
    chain.append(f"Por que agora: o regime atual e '{driver.regime}' -- a urgencia reflete a magnitude do sinal.")

    if driver.direction == "negative":
        consequence = "a exposicao permanece sujeita ao regime atual, sem qualquer mitigacao."
    elif driver.direction == "positive":
        consequence = "a oportunidade identificada pode nao ser capturada."
    else:
        consequence = "nenhuma mudanca esperada -- o sinal ainda nao tem vies direcional definido."
    chain.append(f"Se nada for feito: {consequence}")

    chain.append(f"Recomendacao: {recommendation.action}.")
    chain.append(
        f"Confianca ({driver.confidence_label}, {driver.confidence_score:.0%}): baseada na magnitude do "
        f"sinal de regime e na fracao do portfolio efetivamente exposta a ele."
    )
    return chain


def build_for_concentration(concentration, recommendation) -> list[str]:
    """concentration: runtime.exposure.bucket.ConcentrationReport."""
    return [
        (
            f"O que aconteceu: a maior holding representa {concentration.top_holding_weight_pct:.1f}% "
            f"do portfolio (HHI={concentration.hhi:.0f}, escala 0-10000)."
        ),
        "Por que: baixa diversificacao aumenta a sensibilidade do portfolio a eventos especificos de um unico ativo.",
        f"Por que este portfolio: as 5 maiores holdings somam {concentration.top_5_weight_pct:.1f}% do valor total.",
        "Por que importa: concentracao elevada e um fator estrutural de risco, independente do regime macro atual.",
        "Por que agora: e estrutural, nao depende de timing de mercado -- pode ser endereçado a qualquer hora.",
        "Se nada for feito: o portfolio permanece mais exposto a volatilidade idiossincratica das maiores posicoes.",
        f"Recomendacao: {recommendation.action}.",
        "Confianca: baseada diretamente no HHI (Herfindahl-Hirschman), um calculo deterministico, nao uma previsao.",
    ]
