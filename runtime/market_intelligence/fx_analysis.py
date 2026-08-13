"""FX regime analysis — real data only.

Uses the currency observers already registered in runtime/observers
(dxy, eur_usd, usd_cny, usd_jpy, dollar=USDBRL). All tickers verified
live against Yahoo Finance (see market_observers.py expansion notes).

Output per pair: level, day delta %, regime (strengthening/weakening USD
for the pair's convention), and an overall dollar index summary.
"""

from __future__ import annotations

from dataclasses import dataclass

from runtime.observers.registry import registry, ObserverError
from runtime.observers.providers.yfinance_provider import fetch_quote

# source -> description. "dollar" (USDBRL) lives in the legacy observer
# set; the rest are Market Intelligence additions.
FX_SOURCES = [
    ("dxy", "US Dollar Index"),
    ("eur_usd", "EUR/USD"),
    ("usd_cny", "USD/CNY"),
    ("usd_jpy", "USD/JPY"),
    ("dollar", "USD/BRL"),
]

# Convention per pair: does a RISING price mean USD strengthening?
USD_STRENGTH_ON_RISE = {"dxy": True, "eur_usd": False,
                        "usd_cny": True, "usd_jpy": True, "dollar": True}


@dataclass
class FxPair:
    source: str
    name: str
    level: float | None
    delta_pct_1d: float | None
    usd_regime: str  # "strengthening" / "weakening" / "neutral" / "no_data"

    def to_dict(self) -> dict:
        return {"source": self.source, "name": self.name,
                "level": self.level, "delta_pct_1d": self.delta_pct_1d,
                "usd_regime": self.usd_regime}


def analyze_fx() -> dict:
    pairs: list[FxPair] = []
    dxy_delta = None
    for source, name in FX_SOURCES:
        try:
            observer = registry.get(source)
            events = observer.observe()
            payload = events[0].payload if events else {}
        except ObserverError:
            try:
                payload = fetch_quote(_symbol_of(source))
                payload = {"value": payload["price"],
                           "previous_close": payload.get("previous_close")}
            except ObserverError:
                payload = {}
        value = payload.get("value")
        prev = payload.get("previous_close")
        delta = None
        if value is not None and prev:
            delta = round((value - prev) / prev * 100, 2)
        regime = _pair_regime(source, delta)
        pairs.append(FxPair(source=source, name=name, level=value,
                            delta_pct_1d=delta, usd_regime=regime))
        if source == "dxy":
            dxy_delta = delta
    return {"pairs": [p.to_dict() for p in pairs],
            "dxy_delta_pct_1d": dxy_delta}


def _symbol_of(source: str) -> str:
    symbols = {"dxy": "DX-Y.NYB", "eur_usd": "EURUSD=X", "usd_cny": "CNY=X",
               "usd_jpy": "JPY=X", "dollar": "USDBRL=X"}
    return symbols.get(source, source)


def _pair_regime(source: str, delta_pct: float | None) -> str:
    if delta_pct is None:
        return "no_data"
    rising_strengthens = USD_STRENGTH_ON_RISE.get(source, True)
    if abs(delta_pct) < 0.3:
        return "neutral"
    if (delta_pct > 0) == rising_strengthens:
        return "strengthening"
    return "weakening"
