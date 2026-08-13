"""US yield curve analysis — real data only.

Sources: runtime/observers.registry (YFinanceObserver instances for
^IRX/^FVX/^TNX/^TYX = 2Y/5Y/10Y/30Y; note ^IRX is a 13-week T-bill
annualized proxy — the closest real 2Y-range source available in
yfinance; the genuine ^TWOY ticker exists only as an index page and is
unreliable, so the curve is built from IRX/FVX/TNX/TYX with a clear
mapping note).

Brasil (Selic/CDI/DI) has NO confirmed real source today — deliberately
absent rather than faked. See the investigation reports.

Curve states (spread = long - short):
  steepening  -> spread increasing vs prior (reflationary / growth)
  flattening  -> spread narrowing vs prior
  inverted    -> spread <= 0 (historical recession signal)
  parallel    -> no significant movement
"""

from __future__ import annotations

from dataclasses import dataclass

from runtime.observers.registry import registry, ObserverError

# Source -> approximate maturity label, in ascending maturity order.
CURVE_SOURCES = [
    ("treasury_2y", "2Y (IRX ~13wk proxy)"),
    ("treasury_5y", "5Y"),
    ("treasury", "10Y"),
    ("treasury_30y", "30Y"),
]


@dataclass
class CurvePoint:
    source: str
    label: str
    yield_pct: float | None  # percent, e.g. 4.32
    previous_close: float | None


@dataclass
class YieldCurve:
    points: list[CurvePoint]
    slope_10y_2y: float | None  # bps 10Y minus 2Y
    slope_30y_10y: float | None  # bps 30Y minus 10Y
    previous_slope_10y_2y: float | None
    state: str  # "normal", "flat", "inverted", "steepening", "flattening"

    def to_dict(self) -> dict:
        return {
            "points": [
                {"source": p.source, "label": p.label,
                 "yield_pct": p.yield_pct, "previous_close": p.previous_close}
                for p in self.points
            ],
            "slope_10y_2y_bps": self.slope_10y_2y,
            "slope_30y_10y_bps": self.slope_30y_10y,
            "previous_slope_10y_2y_bps": self.previous_slope_10y_2y,
            "state": self.state,
        }


def _fetch(source: str) -> dict:
    try:
        observer = registry.get(source)
        events = observer.observe()
        payload = events[0].payload if events else {}
    except ObserverError:
        return {}
    price = payload.get("value")
    if price is None:
        return {}
    return {"yield_pct": price, "previous_close": payload.get("previous_close")}


def build_yield_curve() -> YieldCurve:
    points: list[CurvePoint] = []
    for source, label in CURVE_SOURCES:
        data = _fetch(source)
        points.append(CurvePoint(
            source=source, label=label,
            yield_pct=data.get("yield_pct"),
            previous_close=data.get("previous_close"),
        ))

    yields = [p.yield_pct for p in points if p.yield_pct is not None]
    if len(yields) < 2:
        return YieldCurve(points=points, slope_10y_2y=None,
                          slope_30y_10y=None, previous_slope_10y_2y=None,
                          state="insufficient_data")

    by_source = {p.source: p.yield_pct for p in points if p.yield_pct is not None}

    def slope(a: str, b: str) -> float | None:
        if a in by_source and b in by_source:
            return round((by_source[b] - by_source[a]) * 100, 1)  # percent -> bps
        return None

    s_10y_2y = slope("treasury_2y", "treasury")
    s_30y_10y = slope("treasury", "treasury_30y")

    prev = {}
    for source, _label in CURVE_SOURCES:
        pc = next((p.previous_close for p in points
                   if p.source == source and p.previous_close is not None), None)
        if pc is not None:
            prev[source] = pc
    prev_slope = None
    if "treasury_2y" in prev and "treasury" in prev:
        prev_slope = round((prev["treasury"] - prev["treasury_2y"]) * 100, 1)

    state = _classify_state(s_10y_2y, prev_slope)
    return YieldCurve(points=points, slope_10y_2y=s_10y_2y,
                      slope_30y_10y=s_30y_10y,
                      previous_slope_10y_2y=prev_slope, state=state)


def _classify_state(slope_bps: float | None, prev_bps: float | None) -> str:
    if slope_bps is None:
        return "insufficient_data"
    if slope_bps <= 0:
        return "inverted"
    if prev_bps is None:
        return "normal" if slope_bps > 100 else "flat"
    delta = slope_bps - prev_bps
    if delta > 10:
        return "steepening"
    if delta < -10:
        return "flattening"
    return "normal" if slope_bps > 100 else "flat"
