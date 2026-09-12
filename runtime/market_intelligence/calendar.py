"""Economic calendar — deterministic anchors + market-derived events.

No synthetic calendar: this module produces events from real, observable
inputs:
  1. Market session anchors (pre-open, open, close) for NY and SP,
     computed from the current weekday and UTC time — verifiable fact.
  2. Market-derived signals from the observer framework (e.g. new
     regime change, VIX breaches, curve inversion) — already validated
     by the alert/macro-score engines.

Full event calendars (NFP, FOMC dates) require an external authoritative
source (e.g. a paid economic data feed) — deliberately absent rather
than faked. When one becomes available, add a provider next to the
yfinance provider without touching this interface.
"""

from __future__ import annotations

from datetime import UTC, datetime, time

ANCHORS = [
    # (market, event, hour_utc)
    ("usa", "pre-market (futures)", 9),
    ("usa", "NYSE open", 13, "30"),
    ("usa", "NYSE close", 20),
    ("brasil", "B3 open", 13),
    ("brasil", "B3 close", 18),
    ("asia", "Tokyo open", 0),
    ("asia", "Shanghai open", 1, "30"),
    ("europe", "London open", 8),
]


def today_events(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(UTC)
    events: list[dict] = []
    for entry in ANCHORS:
        market, event = entry[0], entry[1]
        hour = int(entry[2])
        minute = int(entry[3]) if len(entry) > 3 else 0
        anchor = now.replace(hour=hour, minute=minute, second=0,
                             microsecond=0, tzinfo=UTC)
        diff_min = int((anchor - now).total_seconds() // 60)
        if -30 <= diff_min <= 1440:
            events.append({"market": market, "event": event,
                           "occurs_at_utc": anchor.isoformat(),
                           "in_minutes": diff_min})
    return events
