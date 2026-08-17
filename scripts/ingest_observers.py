#!/usr/bin/env python3
"""Scheduled observer ingestion job (P0 — ingestion contínua).

Executa os 7 observers registrados via `ObserverScheduler.run_once()`,
com as seguintes garantias:

- retry: cada ciclo tenta até MAX_ATTEMPTS com backoff entre tentativas
  (para a Yahoo Finance ser flaky sem abortar o job inteiro);
- registro de erros: cada fonte falha é logada por stderr + linhas de
  status em logs/ingest_job.jsonl (never secrets);
- sem duplicação desnecessária: se o valor mais recente da fonte já foi
  coletado há menos de MIN_AGE_SECONDS, a fonte é pulada naquele ciclo
  (a menos que force seja pedido, p.ex. no primeiro run);
- persistência: eventos vão para o EventRepository (data/flowcore.db),
  exatamente como o scheduler original faz (Sprint 19);
- execução manual: este script roda tanto como job agendado quanto via
  CLI (`python3 scripts/ingest_observers.py`);
- verificável: o arquivo de status mostra última execução, duração e
  erros por fonte; `flowcore.py observer events <source>` mostra o
  histórico real.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from runtime.observers.registry import registry  # noqa: E402
from runtime.observers.base import ObserverError  # noqa: E402
from runtime.observers.event import MarketEvent  # noqa: E402

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 2.0
MIN_AGE_SECONDS = 300  # 5 min entre coletas da mesma fonte (dedup)
STATUS_FILE = ROOT / "logs" / "ingest_job.jsonl"
LOG_LINES = 80  # manter histórico de status enxuto


def _safe_import_repo():
    from storage import EventRepository

    return EventRepository()


def _observe_once(obs) -> list[MarketEvent]:
    """Observa uma fonte; relança ObserverError para o loop de retry."""
    return obs.observe()


def _dedup_window(events: list[dict]) -> bool:
    """True se o evento mais recente da fonte é recente o suficiente."""
    if not events:
        return False
    newest = max(e["timestamp"] for e in events)
    try:
        last = datetime.fromisoformat(newest).replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return False
    age = (datetime.now(UTC) - last).total_seconds()
    return age < MIN_AGE_SECONDS


def _is_forced() -> bool:
    return "--force" in sys.argv


async def _run_source(obs) -> dict:
    """Executa uma fonte com retry. Retorna status por fonte."""

    repo = _safe_import_repo()
    await repo.ensure_tables()

    # Checar janela de dedup antes de gastar rede (consulta leve, já indexada).
    try:
        import aiosqlite

        async with aiosqlite.connect(str(repo._db_path)) as db:
            row = await db.execute(
                "SELECT timestamp FROM market_events WHERE source = ? ORDER BY timestamp DESC LIMIT 1",
                (obs.source,),
            )
            last_row = await row.fetchone()
        if not _is_forced() and last_row and _dedup_window([{"timestamp": last_row[0]}]):
            return {
                "source": obs.source,
                "status": "skipped_fresh",
                "events": 0,
                "error": None,
            }
    except Exception as e:  # dedup é otimização — falhar aqui não impede ingestão
        print(f"[{obs.source}] dedup check falhou (ingestão continua): {e}", file=sys.stderr)

    last_error = None
    collected = 0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            events = await asyncio.to_thread(_observe_once, obs)
            for ev in events:
                try:
                    await repo.insert_event(ev.to_dict())
                    collected += 1
                except Exception as e:
                    print(f"[{obs.source}] persistência falhou: {e}", file=sys.stderr)
            return {
                "source": obs.source,
                "status": "ok" if collected else "empty",
                "events": collected,
                "attempt": attempt,
                "error": None,
            }
        except ObserverError as e:
            last_error = str(e)
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(BACKOFF_SECONDS * attempt)
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(BACKOFF_SECONDS * attempt)
    return {
        "source": obs.source,
        "status": "failed",
        "events": 0,
        "attempt": MAX_ATTEMPTS,
        "error": last_error,
    }


async def main() -> int:
    sources = [a for a in sys.argv[1:] if a != "--force"]
    observers = registry.all()
    if sources:
        unknown = [s for s in sources if s not in registry.names()]
        if unknown:
            print(f"Fontes desconhecidas: {unknown}", file=sys.stderr)
            return 1
        observers = [o for o in observers if o.source in sources]
    if not observers:
        print("Nenhum observer para executar.", file=sys.stderr)
        return 1

    started = time.monotonic()
    results = []
    for obs in observers:
        result = await _run_source(obs)
        results.append(result)
        status = result["status"]
        if status == "ok":
            print(
                f"OK      {obs.source:<10} {result['events']} evento(s)"
                + (f" (tentativa {result['attempt']})" if result["attempt"] > 1 else "")
            )
        elif status == "skipped_fresh":
            print(f"PULADO  {obs.source:<10} dado recente (< {MIN_AGE_SECONDS}s) — use --force para forçar")
        elif status == "empty":
            print(f"VAZIO   {obs.source:<10} sem eventos neste ciclo")
        else:
            print(f"FALHOU  {obs.source:<10} após {MAX_ATTEMPTS} tentativas: {result['error']}", file=sys.stderr)
    duration = time.monotonic() - started

    ok = sum(1 for r in results if r["status"] == "ok")
    failed = sum(1 for r in results if r["status"] == "failed")

    # Status persistente para verificação de última execução / erro.
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "run_at": datetime.now(UTC).isoformat(),
        "duration_seconds": round(duration, 2),
        "observers_total": len(results),
        "observers_ok": ok,
        "observers_failed": failed,
        "per_source": results,
    }
    lines = STATUS_FILE.read_text().splitlines() if STATUS_FILE.exists() else []
    lines = [json.loads(ln) for ln in lines if ln.strip()]
    lines.append(entry)
    if len(lines) > LOG_LINES:
        lines = lines[-LOG_LINES:]
    STATUS_FILE.write_text("\n".join(json.dumps(ln) for ln in lines) + "\n")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
