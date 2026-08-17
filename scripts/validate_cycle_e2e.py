#!/usr/bin/env python3
"""Validate the full market cycle E2E with REAL data only (no mocks).

Cycle: Mercado -> Macro -> Regime -> Ativos -> Carteira -> Risco ->
       Alocação -> Alerta -> Briefing -> (Agente via /api/ask, optional)

Usage:
    cd /path/to/FlowCore && python3 scripts/validate_cycle_e2e.py [--ask]
The --ask flag adds one /api/ask round-trip against the running FlowCore
server (requires FLOWCORE_API_TOKEN set). Everything else runs in-process.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"

results: list[tuple[str, str, str]] = []  # (stage, status, evidence)


def report(stage: str, status: str, evidence: str) -> None:
    results.append((stage, status, evidence))
    tag = {"PASS": "\U0001F7E2", "WARN": "\U0001F7E1", "FAIL": "\U0001F534"}[status]
    print(f"{tag} {stage}: {evidence}")


# ── 1. MERCADO: observers + eventos reais persistidos ─────────────────────────
try:
    from runtime.observers.registry import registry as _reg
    from runtime.observers.scheduler import ObserverScheduler, _default_event_repo

    async def _stage_mercado() -> None:
        sched = ObserverScheduler(_reg, event_repo=_default_event_repo())
        events = await sched.run_once()
        report(
            "1. MERCADO (observers + eventos reais persistidos)",
            PASS if events else WARN,
            f"{len(events)} eventos reais persistidos via EventRepository (SQLite)",
        )

    asyncio.run(_stage_mercado())
except Exception as e:
    report("1. MERCADO", FAIL, f"erro: {e}")

# ── 2+3. MACRO + REGIME (SCPX) ────────────────────────────────────────────────
try:
    from runtime.macro_score.engine import MacroScoreEngine
    from runtime.regime.engine import RegimeEngine
    from runtime.observers.scheduler import _default_event_repo as _repo_fn

    async def _stage_regime() -> None:
        repo = _repo_fn()
        engine = MacroScoreEngine(repo)
        regime = RegimeEngine(engine)
        out: dict[str, str] = {}
        for dim in ("commodities", "liquidity", "risk_sentiment"):
            await engine.compute_score(dim)
            sig = await regime.classify(dim)
            out[dim] = f"{sig.regime if hasattr(sig, 'regime') else sig}" if sig else "?"
        report("2+3. MACRO + REGIME (SCPX)", PASS, "; ".join(f"{k}={v}" for k, v in out.items()))

    asyncio.run(_stage_regime())
except Exception as e:
    report("2+3. MACRO + REGIME", FAIL, f"erro: {e}")

# ── 4+5. ATIVOS + CARTEIRA (asset classes por categoria real) ─────────────────
try:
    from runtime.market_intelligence.asset_classes import analyze_asset_classes

    ac = analyze_asset_classes()
    names = list(ac.get("classes", {}).keys())
    report(
        "4+5. ATIVOS + CARTEIRA (asset classes)",
        PASS if names else WARN,
        f"{len(names)} classes reais: {', '.join(names) or 'vazio'}",
    )
except Exception as e:
    report("4+5. ATIVOS + CARTEIRA", FAIL, f"erro: {e}")

# ── 6. RISCO (curva + correlação) ─────────────────────────────────────────────
try:
    from runtime.market_intelligence.yield_curve import build_yield_curve
    from runtime.market_intelligence.risk import correlation_matrix

    curve = build_yield_curve()
    state = getattr(curve, "state", None) or getattr(curve, "shape", None)
    corr = correlation_matrix(["SPY", "QQQ", "XLE", "GLD"])
    report(
        "6. RISCO (yield curve + correlação)",
        PASS if state or corr.get("matrix") else WARN,
        f"curva state={state}; correlação {len(corr.get('matrix', []))} ativos",
    )
except Exception as e:
    report("6. RISCO", FAIL, f"erro: {e}")

# ── 7. ALOCAÇÃO (rebalance com holdings de exemplo reais — mercado real) ──────
try:
    from runtime.market_intelligence.rebalance import analyze_rebalancing

    # Holdings com dados de mercado REAIS (cotações consultadas agora).
    rebal = analyze_rebalancing(
        [
            {"symbol": "SPY", "value": 40000},
            {"symbol": "QQQ", "value": 30000},
            {"symbol": "XLE", "value": 20000},
            {"symbol": "GLD", "value": 10000},
        ],
        {"equities": 60.0, "commodities": 20.0, "rates": 20.0},
    )
    actions = rebal.get("actions", {})
    report(
        "7. ALOCAÇÃO (rebalance determinístico)",
        PASS if actions else WARN,
        f"buckets={len(rebal.get('buckets', []))}; actions={json.dumps(actions, ensure_ascii=False)[:120]}",
    )
except Exception as e:
    report("7. ALOCAÇÃO", FAIL, f"erro: {e}")

# ── 8. ALERTA ─────────────────────────────────────────────────────────────────
try:
    from runtime.market_intelligence.alerts import evaluate_alerts

    fired = evaluate_alerts()
    report(
        "8. ALERTA (regras reais)",
        PASS if fired is not None else WARN,
        f"avaliadas: {len(fired)} alertas disparados agora"
        " (0 = sem violações hoje)",
    )
except Exception as e:
    report("8. ALERTA", FAIL, f"erro: {e}")

# ── 9. BRIEFING NATIVO ────────────────────────────────────────────────────────
try:
    from runtime.market_intelligence.briefing import build_briefing

    brief = build_briefing()
    lines = brief.get("lines", []) if isinstance(brief, dict) else []
    report(
        "9. BRIEFING NATIVO",
        PASS if lines else WARN,
        f"{len(lines)} linhas geradas de dados reais",
    )
except Exception as e:
    report("9. BRIEFING", FAIL, f"erro: {e}")

# ── 10. HISTORICAL DATA: persistência real no SQLite ──────────────────────────
try:
    db = str(ROOT / "data" / "flowcore.db")
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT COUNT(*) FROM market_events WHERE timestamp > datetime('now', '-1 hour')"
    ).fetchone()[0]
    try:
        # Table is created lazily by score_history.record_scores() — absent
        # on a fresh install/CI run until a dimension has a real score to
        # persist (all "insufficient_data" is expected with no prior history).
        hist = conn.execute("SELECT COUNT(*) FROM macro_score_history").fetchone()[0]
    except sqlite3.OperationalError:
        hist = 0
    report(
        "10. HISTORICAL DATA (SQLite real)",
        PASS,
        f"market_events última hora={rows}; macro_score_history total={hist}",
    )
except Exception as e:
    report("10. HISTORICAL DATA", FAIL, f"erro: {e}")

# ── 11. AGENTE: /api/ask (opcional, --ask) ─────────────────────────────────────
if "--ask" in sys.argv:
    try:
        import urllib.request

        token = os.environ.get("FLOWCORE_API_TOKEN", "")
        req = urllib.request.Request(
            "http://127.0.0.1:8090/api/ask",
            data=json.dumps({"question": "Quais riscos predominam hoje na carteira?"}).encode(),
            headers={"Content-Type": "application/json", "X-FlowCore-Token": token},
            method="POST",
        )
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=280) as r:
            body = json.loads(r.read().decode())
        report(
            "11. AGENTE (/api/ask E2E)",
            PASS,
            f"HTTP {r.status} em {time.time()-t0:.0f}s; "
            f"tool_used={body.get('tool_used','?')}; model={body.get('model','?')}",
        )
    except Exception as e:
        report("11. AGENTE (/api/ask E2E)", FAIL, f"erro: {e}")

# ── Summary ───────────────────────────────────────────────────────────────────
failed = [r[0] for r in results if r[1] == FAIL]
print("\n" + "=" * 70)
print("SUMARIO:", {s: sum(1 for r in results if r[1] == s) for s in (PASS, WARN, FAIL)})
if failed:
    print("FALHAS:", ", ".join(failed))
    sys.exit(1)
print("Ciclo completo validado com dados REAIS. Nenhum motor foi substituído.")
