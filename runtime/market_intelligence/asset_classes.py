"""Asset class analysis — composed from the existing Observer/MarketEvent
framework. No new data source: every number here comes from a real
yfinance-backed observer already registered (rates, FX, equities,
commodities, volatility).

Each asset class summarizes its observed sources: last value, 1-day
delta, and a directional posture derived from the sign of the delta
(relative to previous close — no fabricated signals).
"""

from __future__ import annotations

from runtime.observers.registry import registry, ObserverError

# Human-readable labels used by the dashboard/Mercado tab.
CLASS_LABELS = {
    "rates": "Taxas (Treasuries)",
    "fx": "Câmbio",
    "equities": "Bolsas (Equities)",
    "commodities": "Commodities",
    "volatility": "Volatilidade",
}


def analyze_asset_classes() -> dict:
    result: dict = {"classes": {}, "updated_at": None}
    for observer in registry.all():
        try:
            events = observer.observe()
        except ObserverError:
            continue
        if not events:
            continue
        event = events[0]
        cls = event.category
        value = event.payload.get("value")
        delta = event.payload.get("delta_pct") or event.payload.get("delta_bps")
        delta_label = "bps" if "delta_bps" in event.payload else "pct"
        posture = _posture(event.payload)
        cls_data = result["classes"].setdefault(
            cls, {"name": CLASS_LABELS.get(cls, cls), "sources": [], "values": []})
        cls_data["sources"].append({
            "source": event.source, "symbol": event.symbol,
            "value": value,
            "delta": delta, "delta_unit": delta_label,
            "posture": posture, "timestamp": event.timestamp,
        })
        cls_data["values"].append(value)
    return result


def _posture(payload: dict) -> str:
    delta = payload.get("delta_pct")
    if delta is None:
        return "no_data"
    if abs(delta) < 0.5:
        return "neutral"
    return "up" if delta > 0 else "down"
