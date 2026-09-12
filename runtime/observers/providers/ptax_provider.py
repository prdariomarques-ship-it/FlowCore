"""Banco Central do Brasil PTAX provider — fallback USD/BRL source.

The "Câmbio" market group (config/market_thresholds.py) has a single
indicator, the dollar, backed by yfinance's USDBRL=X. That is a single
point of failure: any Yahoo Finance hiccup (rate limiting, a delisted
flag, a timeout) empties the whole tab, unlike Índices/Commodities/Juros
which each have several indicators and survive one failure.

PTAX is the Central Bank's own official daily USD/BRL fixing rate,
published once per business day (~13h Brasília time) via a public,
unauthenticated OData API — an independent source that never depends on
Yahoo Finance's availability. It is not a live streaming quote like
yfinance's, but close enough for this dashboard's daily-change display,
and used only as a fallback: yfinance stays primary (same cadence and
shape as the rest of "Câmbio"), this only fires when it fails.
"""

from __future__ import annotations

import datetime as _dt
import json
import urllib.request

from runtime.observers.base import ObserverError

_BASE_URL = "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/CotacaoDolarDia(dataCotacao=@dataCotacao)"
_TIMEOUT_SECONDS = 6.0
# PTAX has no quotation on weekends/holidays -- look back far enough to
# cross a long weekend (e.g. Carnaval, a national holiday on a Monday)
# and still find the last two business-day fixings.
_MAX_LOOKBACK_DAYS = 10


def _fetch_day(date: _dt.date) -> float | None:
    """The day's PTAX 'venda' (sell) quote, or None if the Central Bank
    published nothing for that date (weekend/holiday) -- not an error,
    just an empty day to skip past."""
    date_str = date.strftime("%m-%d-%Y")
    url = f"{_BASE_URL}?@dataCotacao='{date_str}'&$format=json"
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SECONDS) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ObserverError(f"PTAX request failed for {date_str}: {exc}") from exc
    values = data.get("value") or []
    if not values:
        return None
    # BCB sometimes publishes more than one fixing for a date (rare,
    # intraday correction) -- the last one is the day's official close.
    return values[-1].get("cotacaoVenda")


def fetch_usdbrl_ptax() -> dict:
    """Latest PTAX quote plus the prior business day's, shaped like
    yfinance_provider.fetch_quote()'s return value so watchlist.py can
    use it as a drop-in fallback for USDBRL=X.

    Raises ObserverError if no quotation was published in the last
    _MAX_LOOKBACK_DAYS days (a real outage, not just a weekend).
    """
    found: list[float] = []
    day = _dt.date.today()
    for _ in range(_MAX_LOOKBACK_DAYS):
        value = _fetch_day(day)
        if value is not None:
            found.append(value)
            if len(found) == 2:
                break
        day -= _dt.timedelta(days=1)
    if not found:
        raise ObserverError(f"No PTAX quotation available in the last {_MAX_LOOKBACK_DAYS} days")
    price = found[0]
    previous_close = found[1] if len(found) > 1 else None
    return {"symbol": "USDBRL=PTAX", "price": price, "previous_close": previous_close}
