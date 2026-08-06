"""Evaluate a DriverRule against actual regime state + a portfolio's
holdings, producing a DriverImpact (Sprint 23).

Classification always happens in the rule's "elevated" orientation first
(_classify_holding never sees which regime state is active); the actual
regime state only decides, at aggregation time, whether the
elevated-oriented positive/negative sets are used as-is (regime
"elevated"), swapped (regime "depressed"), or shown for information only
with direction forced to "neutral" (regime "neutral" — a driver that
hasn't actually fired is never assigned a sentiment). This keeps a single
classification pass consistent regardless of regime state, instead of
threading an "elevated: bool" through the matching logic itself.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from runtime.impact.models import DriverImpact, ImpactBucket
from runtime.impact.rules import RULES, DriverRule
from runtime.regime.signal import RegimeSignal

__all__ = ["ImpactError", "evaluate"]


class ImpactError(RuntimeError):
    """Raised for an unknown impact dimension."""


_RECOGNIZED_LEVELS = {
    "alta": "high",
    "alto": "high",
    "high": "high",
    "media": "medium",
    "média": "medium",
    "medio": "medium",
    "médio": "medium",
    "medium": "medium",
    "baixa": "low",
    "baixo": "low",
    "low": "low",
}

_EXPECTED_IMPACT_THRESHOLDS = (
    (40.0, "strong"),
    (15.0, "moderate"),
)


def _confidence_score(regime: RegimeSignal) -> float:
    if regime.regime == "insufficient_data" or regime.score is None:
        return 0.0
    return round(min(0.95, 0.5 + abs(regime.score) / 6.0), 2)


def _confidence_label(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


def _expected_impact_label(exposed_weight_pct: float) -> str:
    if exposed_weight_pct <= 0:
        return "none"
    for threshold, label in _EXPECTED_IMPACT_THRESHOLDS:
        if exposed_weight_pct >= threshold:
            return label
    return "mild"


def _soft_attribute_side(holding: dict, rule: DriverRule) -> str | None:
    if not rule.soft_attribute:
        return None
    asset = holding.get("asset") or {}
    raw = (asset.get("attributes") or {}).get(rule.soft_attribute)
    if not raw:
        return None
    level = _RECOGNIZED_LEVELS.get(str(raw).strip().lower())
    if level == "high" and "high" in rule.soft_attribute_negative_values:
        return "negative"
    if level == "low" and "low" in rule.soft_attribute_positive_values:
        return "positive"
    return None  # "medium" or unrecognized text -> fall through to hard baseline


def _hard_baseline_side(holding: dict, rule: DriverRule) -> str | None:
    """Category-only classification (sector / asset_class / country) —
    never a specific ticker or product. See rules.py's module docstring
    for why: turning a generic exposure signal into a concrete product is
    runtime/product_mapping/'s job, not this engine's."""
    asset = holding.get("asset") or {}
    sector = asset.get("sector")
    asset_class = asset.get("asset_class")
    country = asset.get("country")

    if sector in rule.negative_sectors_when_elevated:
        return "negative"
    if sector in rule.positive_sectors_when_elevated:
        return "positive"
    if asset_class in rule.positive_asset_classes_when_elevated:
        return "positive"
    if asset_class in rule.negative_asset_classes_when_elevated:
        return "negative"
    if rule.em_proxy_negative_when_elevated and country and country != "United States":
        return "negative"
    return None


def _classify_holding(holding: dict, rule: DriverRule) -> tuple[str | None, str]:
    """Returns (side, source) in the rule's elevated orientation. side is
    "positive"/"negative"/None; source is "soft"/"hard" (only meaningful
    when side is not None)."""
    soft_side = _soft_attribute_side(holding, rule)
    if soft_side is not None:
        return soft_side, "soft"
    return _hard_baseline_side(holding, rule), "hard"


def _bucket_label(holding: dict, rule: DriverRule, source: str) -> str:
    asset = holding.get("asset") or {}
    sector = asset.get("sector")
    if sector:
        return sector
    if source == "hard":
        asset_class = asset.get("asset_class")
        if (
            asset_class in rule.positive_asset_classes_when_elevated
            or asset_class in rule.negative_asset_classes_when_elevated
        ):
            return asset_class
        country = asset.get("country")
        if rule.em_proxy_negative_when_elevated and country:
            return f"{country} (nao-EUA)"
    return "Unclassified"


def _make_buckets(
    holdings_with_source: list[tuple[dict, str]], rule: DriverRule, direction: str, total: float
) -> list[ImpactBucket]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for h, source in holdings_with_source:
        label = _bucket_label(h, rule, source)
        groups[(label, source)].append(h)

    buckets = []
    for (label, source), group_holdings in groups.items():
        market_value = sum(h["market_value"] for h in group_holdings)
        buckets.append(
            ImpactBucket(
                label=label,
                matched_direction=direction,
                source=source,
                market_value=market_value,
                weight_pct=(market_value / total * 100) if total else 0.0,
                holding_count=len(group_holdings),
                symbols=[h["symbol"] for h in group_holdings],
            )
        )
    return buckets


def _insufficient_data_impact(dimension: str) -> DriverImpact:
    rule = RULES[dimension]
    return DriverImpact(
        dimension=dimension,
        driver=f"{rule.driver_when_elevated} / {rule.driver_when_depressed}",
        regime="insufficient_data",
        regime_score=None,
        direction="insufficient_data",
        expected_impact="none",
        confidence_score=0.0,
        confidence_label="low",
        exposed_weight_pct=0.0,
        positive_weight_pct=0.0,
        negative_weight_pct=0.0,
        reason="Dados macro insuficientes para este indicador ainda.",
    )


def evaluate(holdings: list[dict], regime: RegimeSignal) -> DriverImpact:
    """Build the DriverImpact for one macro dimension against a
    portfolio's already-enriched holdings (service.list_holdings()'s
    output — live market_value + asset classification joined in, exactly
    like ExposureEngine consumes them)."""
    if regime.dimension not in RULES:
        raise ImpactError(f"Unknown impact dimension: {regime.dimension!r}")
    rule = RULES[regime.dimension]

    if regime.regime == "insufficient_data":
        return _insufficient_data_impact(regime.dimension)

    valued = [h for h in holdings if h.get("market_value") is not None]
    total = sum(h["market_value"] for h in valued)

    elevated_positive: list[tuple[dict, str]] = []
    elevated_negative: list[tuple[dict, str]] = []
    for h in valued:
        side, source = _classify_holding(h, rule)
        if side == "positive":
            elevated_positive.append((h, source))
        elif side == "negative":
            elevated_negative.append((h, source))

    if regime.regime == "depressed":
        # depressed is the exact inverse of the elevated orientation.
        positive_group, negative_group = elevated_negative, elevated_positive
        driver = rule.driver_when_depressed
        reason = rule.reason_when_depressed
    else:
        positive_group, negative_group = elevated_positive, elevated_negative
        driver = (
            rule.driver_when_elevated
            if regime.regime == "elevated"
            else (f"{rule.driver_when_elevated} / {rule.driver_when_depressed} (neutro no momento)")
        )
        reason = (
            rule.reason_when_elevated
            if regime.regime == "elevated"
            else "Sinal macro neutro no momento - sem vies direcional claro."
        )

    positive_value = sum(h["market_value"] for h, _ in positive_group)
    negative_value = sum(h["market_value"] for h, _ in negative_group)
    positive_pct = (positive_value / total * 100) if total else 0.0
    negative_pct = (negative_value / total * 100) if total else 0.0
    exposed_pct = positive_pct + negative_pct

    if regime.regime == "neutral":
        direction = "neutral"
    elif negative_pct > positive_pct and negative_pct > 0:
        direction = "negative"
    elif positive_pct > negative_pct and positive_pct > 0:
        direction = "positive"
    else:
        direction = "neutral"

    confidence_score = _confidence_score(regime)
    buckets = _make_buckets(positive_group, rule, "positive", total) + _make_buckets(
        negative_group, rule, "negative", total
    )
    buckets.sort(key=lambda b: b.weight_pct, reverse=True)

    if direction == "positive":
        matched = positive_group
    elif direction == "negative":
        matched = negative_group
    else:
        matched = []
    affected_symbols = sorted({h["symbol"] for h, _ in matched})
    affected_asset_classes = sorted(
        {(h.get("asset") or {}).get("asset_class") for h, _ in matched if (h.get("asset") or {}).get("asset_class")}
    )

    return DriverImpact(
        dimension=regime.dimension,
        driver=driver,
        regime=regime.regime,
        regime_score=regime.score,
        direction=direction,
        expected_impact=_expected_impact_label(exposed_pct),
        confidence_score=confidence_score,
        confidence_label=_confidence_label(confidence_score),
        exposed_weight_pct=round(exposed_pct, 2),
        positive_weight_pct=round(positive_pct, 2),
        negative_weight_pct=round(negative_pct, 2),
        reason=reason,
        buckets=buckets,
        affected_symbols=affected_symbols,
        affected_asset_classes=affected_asset_classes,
        computed_at=datetime.now(UTC).isoformat(),
    )
