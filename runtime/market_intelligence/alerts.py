"""Market alert engine — deterministic thresholds over real observer data.

Rule-free by design: alerts fire ONLY on numeric breaches configured via
ALERT_DEFAULTS (delta % per day, absolute levels). Severity levels:
info / warning / critical. Dedup window of 24h per (rule, source) so the
same breach doesn't spam.

Alerts are persisted to SQLite alongside the rest of FlowCore's
`data/flowcore.db` (table `market_alerts`). Dispatch (WhatsApp/Telegram/
notify endpoint) is the caller's job — `list_alerts()` feeds it.
"""

from __future__ import annotations

import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from runtime.observers.registry import registry, ObserverError

ALERT_DEFAULTS: dict[str, dict] = {
    "vix_absolute": {"source": "vix", "kind": "above", "threshold": 25.0,
                     "severity": "warning", "label": "VIX acima de 25 (risco elevado)"},
    "vix_critical": {"source": "vix", "kind": "above", "threshold": 35.0,
                     "severity": "critical", "label": "VIX acima de 35 (estresse severo)"},
    "treasury_10y_above": {"source": "treasury", "kind": "above",
                           "threshold": 5.0, "severity": "warning",
                           "label": "Treasury 10Y acima de 5%"},
    "usdbrl_above": {"source": "dollar", "kind": "above", "threshold": 6.0,
                     "severity": "warning", "label": "Dólar acima de R$ 6,00"},
    "sp500_daily_drop": {"source": "sp500", "kind": "daily_delta_below",
                         "threshold": -3.0, "severity": "critical",
                         "label": "S&P 500 cai mais de 3% no dia"},
    "ibovespa_daily_drop": {"source": "ibovespa", "kind": "daily_delta_below",
                            "threshold": -3.0, "severity": "critical",
                            "label": "Ibovespa cai mais de 3% no dia"},
    # ── Market Intelligence expansion (2026-08-13) ──────────────────────
    "oil_shock": {"source": "wti", "kind": "daily_delta_above",
                  "threshold": 5.0, "severity": "critical",
                  "label": "WTI sobe mais de 5% no dia (choque de petróleo)"},
    "gold_new_high": {"source": "gold", "kind": "above", "threshold": 4500.0,
                      "severity": "warning",
                      "label": "Ouro acima de US$ 4.500/oz (novo patamar)"},
    "dxy_strong_move": {"source": "dxy", "kind": "daily_delta_above",
                        "threshold": 1.5, "severity": "warning",
                        "label": "DXY move mais de 1,5% no dia (regime FX)"},
    "nasdaq_drop": {"source": "nasdaq", "kind": "daily_delta_below",
                    "threshold": -3.0, "severity": "critical",
                    "label": "Nasdaq cai mais de 3% no dia"},
    "silver_mover": {"source": "silver", "kind": "daily_delta_above",
                     "threshold": 4.0, "severity": "warning",
                     "label": "Prata move mais de 4% no dia"},
    "copper_demand_signal": {"source": "copper", "kind": "daily_delta_below",
                             "threshold": -4.0, "severity": "warning",
                             "label": "Cobre cai mais de 4% no dia (sinal de demanda)"},
}

_DEDUP_HOURS = 24

# Keyed by resolved db_path so tests using distinct temp databases (or
# scripts/service.py's own callers) get independent caches, same
# isolation shape as source_catalog.py's own single-slot cache.
_EVALUATION_CACHE_TTL_SECONDS = 60
_last_evaluation: dict[str, float] = {}


def reset_evaluation_cache(db_path: str | None = None) -> None:
    """Clears the evaluate_alerts() TTL cache for one db_path, or all of
    them if db_path is omitted -- mirrors runtime.rate_limit.reset_rate_limit()."""
    if db_path is None:
        _last_evaluation.clear()
    else:
        _last_evaluation.pop(db_path, None)


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE IF NOT EXISTS market_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule TEXT NOT NULL, source TEXT NOT NULL,
        severity TEXT NOT NULL, label TEXT,
        payload TEXT NOT NULL, fired_at TEXT NOT NULL)""")
    conn.commit()
    return conn


def _default_db_path() -> str:
    import os
    base = os.environ.get("FLOWCORE_DATA_DIR", os.path.expanduser("~/.flowcore"))
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "flowcore.db")


def _observe(source: str) -> list:
    try:
        return registry.get(source).observe()
    except ObserverError:
        return []


def evaluate_alerts(db_path: str | None = None) -> list[dict]:
    """Evaluate all configured rules against live observer data.

    Returns newly fired alerts (after dedup) as dicts, also persisting
    them to SQLite. Silent on any observer failure (graceful degradation
    — an observer down never blocks the others).

    Observers are fetched in parallel. Each one is a network call with its
    own multi-second timeout (yfinance_provider allows up to ~10s plus
    retries), and ALERT_DEFAULTS lists 11 of them: run sequentially, a
    couple of slow or timed-out sources alone pushed this past 19s, which
    is what /api/market/overview was blocking on.

    Real-device evidence (FlowCore Mobile, Cloudflare and Tailscale routes
    both timing out on /api/market/overview): even fanned out in parallel,
    an 11-way concurrent yfinance sweep on a constrained mobile uplink can
    still take long enough to blow past the caller's own timeout — and
    /api/market/overview calls this on EVERY request just to keep the
    alerts table warm (its own comment), never using this function's
    return value directly (list_alerts() reads the DB separately). A
    short TTL cache on the sweep itself, same idea as source_snapshot()'s,
    means a burst of overview requests pays the live-fetch cost once."""
    resolved_db_path = db_path or _default_db_path()
    now = time.monotonic()
    last_run = _last_evaluation.get(resolved_db_path)
    if last_run is not None and now - last_run < _EVALUATION_CACHE_TTL_SECONDS:
        return []
    _last_evaluation[resolved_db_path] = now

    conn = _connect(resolved_db_path)
    cutoff = (datetime.now(UTC) - timedelta(hours=_DEDUP_HOURS)).isoformat()
    fired: list[dict] = []
    seen = set(row[0] for row in conn.execute(
        "SELECT rule FROM market_alerts WHERE fired_at >= ?", (cutoff,)))
    pending = {name: rule for name, rule in ALERT_DEFAULTS.items() if name not in seen}
    with ThreadPoolExecutor(max_workers=max(len(pending), 1), thread_name_prefix="alert-observer") as executor:
        futures = {name: executor.submit(_observe, rule["source"]) for name, rule in pending.items()}
        results = {name: future.result() for name, future in futures.items()}
    for rule_name, rule in pending.items():
        events = results[rule_name]
        if not events:
            continue
        event = events[0]
        value = event.payload.get("value")
        if value is None:
            continue
        breach = _check_breach(rule, event.payload, value)
        if not breach:
            continue
        alert = {"rule": rule_name, "source": rule["source"],
                 "severity": rule["severity"], "label": rule["label"],
                 "payload": {"value": value, **event.payload},
                 "fired_at": datetime.now(UTC).isoformat()}
        conn.execute("INSERT INTO market_alerts (rule, source, severity, label, payload, fired_at) "
                     "VALUES (?,?,?,?,?,?)",
                     (alert["rule"], alert["source"], alert["severity"],
                      alert["label"], json.dumps(alert["payload"]), alert["fired_at"]))
        fired.append(alert)
    conn.commit()
    conn.close()
    return fired


def _check_breach(rule: dict, payload: dict, value: float) -> bool:
    kind = rule["kind"]
    threshold = rule["threshold"]
    if kind == "above":
        return value > threshold
    if kind == "below":
        return value < threshold
    if kind == "daily_delta_below":
        delta = payload.get("delta_pct")
        return delta is not None and delta < threshold
    if kind == "daily_delta_above":
        delta = payload.get("delta_pct")
        return delta is not None and delta > threshold
    return False


def list_alerts(db_path: str | None = None, limit: int = 50) -> list[dict]:
    conn = _connect(db_path or _default_db_path())
    rows = conn.execute(
        "SELECT rule, source, severity, label, payload, fired_at "
        "FROM market_alerts ORDER BY fired_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    out: list[dict] = []
    for rule, source, severity, label, payload, fired_at in rows:
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            payload = {}
        out.append({"rule": rule, "source": source, "severity": severity,
                    "label": label, "payload": payload, "fired_at": fired_at})
    return out
