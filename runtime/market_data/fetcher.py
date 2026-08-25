"""Live market snapshot from public sources without synthetic fallbacks."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.request import Request, urlopen

PTAX_URL = "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
SGS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series_id}/dados/ultimos/1?formato=json"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _result(value: float | None, source: str, observation_date: str | None = None, error: str | None = None) -> dict[str, Any]:
    return {
        "value": value,
        "source": source,
        "observation_date": observation_date,
        "retrieved_at": _now(),
        "available": value is not None,
        "error": error,
    }


def _public_json(url: str, timeout: int = 8) -> dict[str, Any] | list[Any]:
    """Fetch public JSON with a descriptive user agent accepted by BCB services."""
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "FlowCore-Market/1.5"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed public provider URLs
        import json
        return json.loads(response.read().decode("utf-8"))


def fetch_brl_usd() -> dict[str, Any]:
    """Latest USD/BRL PTAX sale quote published by Banco Central do Brasil."""
    end = datetime.now(UTC).date()
    start = end - timedelta(days=10)
    try:
        url = (
            f"{PTAX_URL}?@dataInicial='{start.strftime('%m-%d-%Y')}'&"
            f"@dataFinalCotacao='{end.strftime('%m-%d-%Y')}'&%24top=100&%24format=json"
        )
        payload = _public_json(url, timeout=8)
        quotes = payload.get("value", []) if isinstance(payload, dict) else []
        if not quotes:
            raise ValueError("empty_ptax")
        quote = quotes[-1]
        return _result(float(quote["cotacaoVenda"]), "bcb_ptax", quote.get("dataHoraCotacao"))
    except Exception as error:
        return _result(None, "bcb_ptax", error=type(error).__name__)


def fetch_sgs(series_id: int, source: str) -> dict[str, Any]:
    """Latest value from an official BCB SGS series."""
    try:
        payload = _public_json(SGS_URL.format(series_id=series_id), timeout=8)
        rows = payload if isinstance(payload, list) else []
        if not rows:
            raise ValueError("empty_sgs")
        latest = rows[-1]
        return _result(float(str(latest["valor"]).replace(",", ".")), source, latest.get("data"))
    except Exception as error:
        return _result(None, source, error=type(error).__name__)


def fetch_ibovespa() -> dict[str, Any]:
    """Latest index level and daily change from Yahoo Finance through yfinance."""
    try:
        import yfinance as yf

        history = yf.Ticker("^BVSP").history(period="5d", auto_adjust=False, timeout=6)
        if history is None or history.empty or len(history) < 2:
            raise ValueError("empty_ibovespa_history")
        close = float(history["Close"].iloc[-1])
        previous = float(history["Close"].iloc[-2])
        change = ((close / previous) - 1) * 100 if previous else None
        observation_date = str(history.index[-1].date())
        return {
            **_result(close, "yahoo_finance", observation_date),
            "change_pct": round(change, 4) if change is not None else None,
        }
    except Exception as error:
        return {**_result(None, "yahoo_finance", error=type(error).__name__), "change_pct": None}


def fetch_snapshot() -> dict[str, Any]:
    """Return real observations; unavailable fields remain null and explain why."""
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="flowcore-market-data") as executor:
        futures = {
            "brl_usd": executor.submit(fetch_brl_usd),
            "selic_rate": executor.submit(fetch_sgs, 1178, "bcb_sgs_1178"),
            "ipca_12m": executor.submit(fetch_sgs, 13522, "bcb_sgs_13522"),
            "ibovespa": executor.submit(fetch_ibovespa),
        }
        results = {key: future.result() for key, future in futures.items()}

    return {
        "brl_usd": results["brl_usd"]["value"],
        "selic_rate": results["selic_rate"]["value"],
        "ipca_12m": results["ipca_12m"]["value"],
        "ibov_last": results["ibovespa"]["value"],
        "ibov_change_pct": results["ibovespa"].get("change_pct"),
        "observations": results,
        "timestamp": _now(),
        "available": any(item["available"] for item in results.values()),
        "stub": False,
    }
