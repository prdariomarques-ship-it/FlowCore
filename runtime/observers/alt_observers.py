"""Alternative-source Observers (TradingEconomics + Frankfurter).

Same generic, parameterized design as YFinanceObserver in
market_observers.py: one class per provider, configured by table. These
observers are registered as *complementary* sources — they enrich the
event stream but never replace the primary yfinance observers. A slow or
failing alternative provider only degrades gracefully (its observer
raises ObserverError and the scheduler logs it), never breaking the
primary pipeline.

Sources verified live on 2026-08-20 (see provider docstring for pages).
"""
from __future__ import annotations

from runtime.observers.base import Observer, ObserverError
from runtime.observers.event import new_event
from runtime.observers.providers.alt_provider import (
    fetch_frankfurter,
    fetch_tradingeconomics,
)


class TradingEconomicsObserver(Observer):
    def __init__(self, *, source: str, category: str, page: str, event_name: str, unit: str) -> None:
        self.source = source
        self.category = category
        self.page = page
        self.event_name = event_name
        self.unit = unit  # "pct" or "price"
        self._last_value: float | None = None

    def observe(self) -> list[MarketEvent]:
        data = fetch_tradingeconomics(self.page)
        value = data["value"]
        prior = self._last_value
        self._last_value = value
        payload: dict = {"value": value, "date": data.get("date")}
        if data.get("delta_pct") is not None:
            payload["delta_pct"] = data["delta_pct"]
        if prior is None:
            event_name = "initial_observation"
        else:
            event_name = self.event_name
            delta = value - prior
            if self.unit == "pct":
                payload["delta_bps"] = delta * 100
            else:
                payload["delta_pct"] = (delta / prior * 100) if prior else None
        return [
            new_event(
                source=self.source,
                category=self.category,
                symbol=self.page,
                event=event_name,
                payload=payload,
                metadata={"provider": "tradingeconomics"},
            )
        ]


class FrankfurterObserver(Observer):
    """FX observer backed by the keyless Frankfurter API."""

    def __init__(self, *, source: str, category: str, base: str, to: str, event_name: str) -> None:
        self.source = source
        self.category = category
        self.base = base
        self.to = to
        self.event_name = event_name
        self._last_value: float | None = None

    def observe(self) -> list[MarketEvent]:
        data = fetch_frankfurter(self.to, self.base)
        rates = data["rates"]
        value = rates.get(self.to)
        if value is None:
            raise ObserverError(f"Frankfurter missing rate {self.base}->{self.to}")
        prior = self._last_value
        self._last_value = value
        payload: dict = {"value": value, "base": self.base, "date": data.get("date")}
        if prior is None:
            event_name = "initial_observation"
        else:
            event_name = self.event_name
            delta = value - prior
            payload["delta_pct"] = (delta / prior * 100) if prior else None
        return [
            new_event(
                source=self.source,
                category=self.category,
                symbol=f"{self.base}{self.to}",
                event=event_name,
                payload=payload,
                metadata={"provider": "frankfurter"},
            )
        ]
