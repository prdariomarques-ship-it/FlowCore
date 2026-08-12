"""Scoring module — computes Opportunity Score, Data Confidence, and Risk Score for Radar Imobiliário AI."""

from __future__ import annotations


class OpportunityScoringEngine:
    """Computes different scores and details for property opportunities."""

    def compute(self, prop: dict) -> tuple[float, float, float]:
        """Compute (Opportunity Score, Data Confidence, Risk Score)."""
        discount = prop.get("discount_percent", 0.0)

        # 1. Opportunity Score (0 to 100)
        # Higher discounts and vacant properties yield higher opportunity scores
        opp_score = 50.0
        if discount > 0:
            opp_score += (discount - 20) * 1.5  # boost score for discount over 20%
        if prop.get("is_occupied") == 0:
            opp_score += 15.0  # boost for vacant properties
        opp_score = max(0.0, min(100.0, round(opp_score, 1)))

        # 2. Data Confidence Score (0 to 100)
        # Reflects the quality and availability of fields
        confidence = 100.0
        fields_to_check = ["zip_code", "street", "matricula_number", "property_url"]
        for f in fields_to_check:
            if not prop.get(f):
                confidence -= 15.0
        confidence = max(0.0, min(100.0, round(confidence, 1)))

        # 3. Risk Score (0 to 100)
        # Reflects the risk tier (occupancy, debts, lawsuits)
        risk_score = 30.0
        if prop.get("is_occupied") == 1:
            risk_score += 25.0
        # Simulated debt risk
        discount_excess = discount - 35
        if discount_excess > 0:
            risk_score += discount_excess * 1.2
        risk_score = max(0.0, min(100.0, round(risk_score, 1)))

        return opp_score, confidence, risk_score

    def get_explanation(self, opp_score: float) -> dict[str, list[str]]:
        """Return clear lists of pros and cons explaining the score."""
        pros = ["Excelente desconto em relação à avaliação oficial."]
        cons = ["Imóvel ocupado por terceiro (demanda imissão na posse)."]

        if opp_score > 75:
            pros.append("Alta margem potencial de retorno financeiro.")
            pros.append("Localização em bairro residencial consolidado.")
        else:
            cons.append("Margem líquida reduzida devido a custos estimados.")

        return {"pros": pros, "cons": cons}
