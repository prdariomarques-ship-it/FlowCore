"""Deterministic rebalancing analysis — target vs current allocation.

Compares a user-defined TARGET allocation (fractions per bucket) against
the CURRENT allocation derived from portfolio holdings (converted to the
same buckets via a simple classification table). Output per bucket:

  weight, target, deviation, action (BUY / REDUCE / HOLD / WATCH), reason

Rules (deterministic, no LLM, no invention):
- action = REDUCE when deviation >  +THRESHOLD (excess),
           BUY    when deviation <  -THRESHOLD (shortfall),
           WATCH  when |deviation| is within (THRESHOLD*0.6, THRESHOLD],
           HOLD   otherwise;
- THRESHOLD defaults to 5 percentage points (configurable);
- buckets present in current but missing in target are flagged as
  "UNTARGETED" (the human decides — never auto-deleted);
- buckets present in target but missing in current are flagged as
  "MISSING" with BUY;
- current weights come from holdings only when holdings exist; an empty
  portfolio returns insufficient_data rather than zeros.

Execution of trades is NEVER performed here — this module only produces
the analysis for the human to decide.
"""

from __future__ import annotations

DEFAULT_THRESHOLD_PCT = 5.0

# Bucket classification by substring. Kept minimal on purpose — expanding
# requires real market-knowledge work, not guesswork.
_SYMBOL_TO_BUCKET: list[tuple[str, str]] = [
    ("^", "equities_index"),
    (".SS", "equities_international"),
    ("=X", "fx"),
    ("=F", "commodities"),
    ("SGOV", "cash_short_duration"),
    ("BIL", "cash_short_duration"),
    ("TFLO", "cash_short_duration"),
    ("TLT", "fixed_income_long"),
    ("TIP", "fixed_income_inflation_linked"),
    ("GLD", "gold"),
    ("IAU", "gold"),
    ("DBC", "commodities"),
    ("VUG", "equities_us_growth"),
]


def _bucket_for(symbol: str) -> str:
    upper = symbol.upper()
    for pattern, bucket in _SYMBOL_TO_BUCKET:
        if pattern in upper:
            return bucket
    return "other"


def analyze_rebalancing(
    holdings: list[dict] | None,
    target: dict[str, float] | None,
    threshold_pct: float = DEFAULT_THRESHOLD_PCT,
) -> dict:
    if not holdings:
        return {"error": "insufficient_data", "detail": "no holdings available",
                "buckets": [], "actions": {}}

    # Current weights per bucket from holdings (assume a `value` field;
    # fall back to `quantity` if values are absent).
    bucket_value: dict[str, float] = {}
    for h in holdings:
        sym = h.get("symbol") or ""
        value = h.get("value") or h.get("quantity") or 0.0
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        bucket_value[_bucket_for(sym)] = bucket_value.get(_bucket_for(sym), 0.0) + value

    total = sum(bucket_value.values())
    if total <= 0:
        return {"error": "insufficient_data", "detail": "holdings sum to zero",
                "buckets": [], "actions": {}}

    current = {b: round(v / total * 100, 2) for b, v in bucket_value.items()}

    if not target:
        return {"error": "insufficient_data",
                "detail": "target allocation not provided",
                "buckets": [{"bucket": b, "weight_pct": w} for b, w in current.items()],
                "actions": {}}

    target_pct = {b: round(t * 100, 2) for b, t in target.items()}
    all_buckets = sorted(set(list(current) + list(target_pct)))

    buckets: list[dict] = []
    actions: dict[str, dict] = {}
    for b in all_buckets:
        w = current.get(b, 0.0)
        t = target_pct.get(b, 0.0)
        dev = round(w - t, 2)
        if b in current and b not in target_pct:
            act, reason = "WATCH", "presente na carteira sem peso definido no target"
        elif b not in current:
            act, reason = "BUY", "target definido sem posição atual"
        elif abs(dev) > threshold_pct:
            act = "REDUCE" if dev > 0 else "BUY"
            reason = (f"desvio de {dev:+.1f} p.p. supera o limite de {threshold_pct:g} p.p.")
        elif abs(dev) > threshold_pct * 0.6:
            act, reason = "WATCH", f"desvio de {dev:+.1f} p.p. se aproximando do limite"
        else:
            act, reason = "HOLD", f"desvio de {dev:+.1f} p.p. dentro da banda"
        buckets.append({"bucket": b, "weight_pct": w, "target_pct": t,
                        "deviation_pct": dev})
        actions[b] = {"action": act, "reason": reason}

    return {"error": None, "buckets": buckets, "actions": actions,
            "threshold_pct": threshold_pct}
