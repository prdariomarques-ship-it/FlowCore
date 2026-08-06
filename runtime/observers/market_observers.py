"""Concrete yfinance-backed Observers.

One generic, parameterized class rather than five near-identical ones —
adding a new yfinance-backed source is one more instantiation (see the
bottom of this file / registry.py), zero changes to existing code
(Open/Closed). Non-yfinance future observers (news, Fed statements, ...)
would subclass Observer directly instead of this class.
"""

from __future__ import annotations

from runtime.observers.base import Observer
from runtime.observers.event import MarketEvent, new_event
from runtime.observers.providers.yfinance_provider import fetch_quote


class YFinanceObserver(Observer):
    def __init__(self, *, source: str, category: str, symbol: str, event_name: str, unit: str) -> None:
        self.source = source
        self.category = category
        self.symbol = symbol
        self.event_name = event_name
        self.unit = unit  # "pct" (yields, delta in bps) or "price" (delta in %)
        self._last_value: float | None = None

    def observe(self) -> list[MarketEvent]:
        quote = fetch_quote(self.symbol)
        price = quote["price"]
        previous_close = quote.get("previous_close")

        prior = self._last_value
        self._last_value = price

        payload: dict = {"value": price, "previous_close": previous_close}
        if prior is None:
            event_name = "initial_observation"
        else:
            event_name = self.event_name
            delta = price - prior
            if self.unit == "pct":
                payload["delta_bps"] = delta * 100
            else:
                payload["delta_pct"] = (delta / prior * 100) if prior else None

        return [
            new_event(
                source=self.source,
                category=self.category,
                symbol=self.symbol,
                event=event_name,
                payload=payload,
                metadata={"provider": "yfinance"},
            )
        ]


def default_yfinance_observers() -> list[YFinanceObserver]:
    return [
        YFinanceObserver(source="treasury", category="rates", symbol="^TNX", event_name="yield_change", unit="pct"),
        YFinanceObserver(source="dollar", category="fx", symbol="USDBRL=X", event_name="fx_change", unit="price"),
        YFinanceObserver(
            source="vix", category="volatility", symbol="^VIX", event_name="volatility_change", unit="price"
        ),
        YFinanceObserver(source="oil", category="commodities", symbol="BZ=F", event_name="price_change", unit="price"),
        YFinanceObserver(source="gold", category="commodities", symbol="GC=F", event_name="price_change", unit="price"),
    ]
