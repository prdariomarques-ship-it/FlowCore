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
        # Japan Duration Risk investigation: these two are the only
        # components of that indicator with a confirmed real data source;
        # the rest (JGB 10Y, Japanese Treasury holdings, FIMA, capital
        # flow) have none today and are NOT observed here rather than
        # faked. No scoring/classification built on these yet -- see the
        # investigation report for why.
        YFinanceObserver(source="usd_jpy", category="fx", symbol="JPY=X", event_name="fx_change", unit="price"),
        YFinanceObserver(source="treasury_30y", category="rates", symbol="^TYX", event_name="yield_change", unit="pct"),
        # ── Market Intelligence expansion (2026-08-13) ──────────────────
        # All tickers below were verified programmatically against
        # yfinance on 13/08/2026 (see data/symbols_verified_20260813.md).
        # Brasil — equity
        YFinanceObserver(
            source="ibovespa", category="equities", symbol="^BVSP", event_name="price_change", unit="price"
        ),
        # EUA — equities
        YFinanceObserver(source="sp500", category="equities", symbol="^GSPC", event_name="price_change", unit="price"),
        YFinanceObserver(source="nasdaq", category="equities", symbol="^IXIC", event_name="price_change", unit="price"),
        YFinanceObserver(source="dow", category="equities", symbol="^DJI", event_name="price_change", unit="price"),
        YFinanceObserver(
            source="russell2000", category="equities", symbol="^RUT", event_name="price_change", unit="price"
        ),
        # EUA — taxa (5Y para completar a curva 2-5-10-30)
        YFinanceObserver(source="treasury_5y", category="rates", symbol="^FVX", event_name="yield_change", unit="pct"),
        YFinanceObserver(source="treasury_2y", category="rates", symbol="^IRX", event_name="yield_change", unit="pct"),
        # EUA — dólar global (DXY via DX-Y.NYB, verificado com retry)
        YFinanceObserver(source="dxy", category="fx", symbol="DX-Y.NYB", event_name="fx_change", unit="price"),
        # Europa
        YFinanceObserver(
            source="eurostoxx", category="equities", symbol="^STOXX50E", event_name="price_change", unit="price"
        ),
        YFinanceObserver(source="dax", category="equities", symbol="^GDAXI", event_name="price_change", unit="price"),
        YFinanceObserver(source="ftse", category="equities", symbol="^FTSE", event_name="price_change", unit="price"),
        YFinanceObserver(source="eurusd", category="fx", symbol="EURUSD=X", event_name="fx_change", unit="price"),
        # Ásia
        YFinanceObserver(
            source="nikkei", category="equities", symbol="^N225",
            event_name="price_change", unit="price",
        ),
        YFinanceObserver(
            source="hangseng", category="equities", symbol="^HSI",
            event_name="price_change", unit="price",
        ),
        YFinanceObserver(
            source="shanghai", category="equities", symbol="000001.SS",
            event_name="price_change", unit="price",
        ),
        YFinanceObserver(source="usdcny", category="fx", symbol="CNY=X", event_name="fx_change", unit="price"),
        # Commodities extras (Brent já coberto por `oil`)
        YFinanceObserver(
            source="wti", category="commodities", symbol="CL=F",
            event_name="price_change", unit="price",
        ),
        YFinanceObserver(
            source="silver", category="commodities", symbol="SI=F",
            event_name="price_change", unit="price",
        ),
        YFinanceObserver(
            source="copper", category="commodities", symbol="HG=F",
            event_name="price_change", unit="price",
        ),
    ]
