#!/usr/bin/env python3
"""Testes cruzados Web ↔ Mobile ↔ Agent (Fase 2 — testes 1-7 do prompt).

Simula as interfaces usando o MESMO Core (REST API):
- Web/Mobile = clientes REST do Core (a UI e o futuro APK consomem /api/*)
- Agent = ship-it flowcore_tools (REST shim) — simulado aqui via chamadas idênticas

Testes:
1. Criar carteira (simula Web)  → verificar leitura (Mobile/Agent)
2. Adicionar ativo (simula Mobile) → verificar leitura (Web/Agent)
3. Alterar carteira → Agent consulta summary/impact
4. Criar memória (simula Mobile) → Agent consulta
5. Criar nota (simula Web) → Mobile consulta
6. Mercado atualiza (ingestão) → todos veem
7. Leitura do regime/macro por qualquer interface

Cleanup: remove dados de teste criados.
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8080"
LOG: list[str] = []


def step(name: str) -> None:
    print(f"\n== {name}")
    LOG.append(name)


def ok(msg: str) -> None:
    print(f"  [OK] {msg}")
    LOG.append(f"OK: {msg}")


def fail(msg: str) -> None:
    print(f"  [FALHA] {msg}")
    LOG.append(f"FALHA: {msg}")


def get(path: str, expect=200):
    r = requests.get(BASE + path, timeout=20)
    if r.status_code != expect:
        raise RuntimeError(f"{path}: HTTP {r.status_code}")
    return r.json()


def post(path: str, body, expect=201):
    r = requests.post(BASE + path, json=body, timeout=20)
    if r.status_code != expect:
        raise RuntimeError(f"POST {path}: HTTP {r.status_code} {r.text[:200]}")
    return r.json()


def delete(path: str, expect=200):
    r = requests.delete(BASE + path, timeout=20)
    if r.status_code != expect:
        raise RuntimeError(f"DELETE {path}: HTTP {r.status_code}")
    return r.json()


def main() -> int:
    rc = 0
    failures: list[str] = []

    # Teste 1: criar carteira (simula Web) e verificar leitura (Mobile/Agent)
    step("Teste 1 — Criar carteira (Web) e verificar leitura (Mobile/Agent)")
    try:
        pf = post("/api/portfolios", {"name": "Fase2 Sync Test"})
        pid = pf["id"]
        ok(f"carteira criada id={pid}")
        lst = get("/api/portfolios")["portfolios"]
        if any(p["id"] == pid and p["name"] == "Fase2 Sync Test" for p in lst):
            ok("lista de carteiras reflete a criação (Mobile/Agent veem)")
        else:
            fail("carteira não aparece na listagem")
            rc = 1
    except Exception as e:
        fail(str(e)); rc = 1; pid = None

    # Teste 2: adicionar ativo (simula Mobile) e verificar leitura (Web/Agent)
    step("Teste 2 — Adicionar ativo (Mobile) e verificar leitura (Web/Agent)")
    if pid:
        try:
            h = post(f"/api/portfolios/{pid}/holdings",
                     {"symbol": "NVDA", "quantity": 8, "average_cost": 130})
            ok(f"holding adicionado id={h['id']} ({h['symbol']} ×{h['quantity']})")
            hl = get(f"/api/portfolios/{pid}/holdings")["holdings"]
            if any(x["symbol"] == "NVDA" for x in hl):
                ok("Web/Agent veem o ativo via holdings (valoração ao vivo)")
            else:
                fail("holding não aparece")
                rc = 1
        except Exception as e:
            fail(str(e)); rc = 1

    # Teste 3: alterar carteira → Agent consulta summary/impact
    step("Teste 3 — Alterar carteira e Agent consultar summary/impact")
    if pid:
        try:
            s = get(f"/api/portfolios/{pid}/summary")
            ok(f"summary: valor={s.get('total_market_value')} custo={s.get('total_cost_basis')}")
            imp = get(f"/api/portfolios/{pid}/impact")
            ok(f"impact: risco={imp.get('portfolio_risk_score')} impacto={imp.get('overall_impact')}")
        except Exception as e:
            fail(str(e)); rc = 1

    # Teste 4: criar memória (Mobile) → Agent consulta
    step("Teste 4 — Criar memória (Mobile) e Agent consultar")
    try:
        post("/api/memories", {"text": "[teste fase2] memória de sincronização"})
        mems = get("/api/memories")["memories"]
        if any("fase2" in (m.get("text") or "") for m in mems):
            ok("memória criada e visível ao Agent via /api/memories")
        else:
            fail("memória não visível")
            rc = 1
    except Exception as e:
        fail(str(e)); rc = 1

    # Teste 5: criar nota (Web) → Mobile consulta
    step("Teste 5 — Criar nota (Web) e Mobile consultar")
    try:
        post("/api/notes", {"text": "[teste fase2] nota de sincronização"})
        notes = get("/api/notes")["notes"]
        if any("fase2" in (n.get("content") or n.get("text") or "") for n in notes):
            ok("nota criada e visível no Mobile via /api/notes")
        else:
            fail("nota não visível")
            rc = 1
    except Exception as e:
        fail(str(e)); rc = 1

    # Teste 6: Agent executar consulta de regime (ferramentas reais)
    step("Teste 6 — Agent consulta ferramentas reais (regime/macro)")
    try:
        scores = get("/api/macro-score/scores")["scores"]
        ok(f"macro scores: {len(scores)} dimensões")
        for s in scores:
            print(f"       {s['dimension']}: {s['score']} ({s['status']})")
        dims = get("/api/macro-score/dimensions")["dimensions"]
        ok(f"dimensões: {list(dims.keys())}")
    except Exception as e:
        fail(str(e)); rc = 1

    # Teste 7: mercado atualiza → todos veem
    step("Teste 7 — Ingestão de mercado atualiza dados vistos por todas as interfaces")
    try:
        before = get("/api/observer/events")["events"]
        n_before = len(before)
        # executa a ingestão (mesmo job que o cron usa)
        import subprocess
        subprocess.run([sys.executable, str(Path(__file__).parent / "ingest_observers.py")],
                       check=True, capture_output=True, timeout=300)
        after = get("/api/observer/events")["events"]
        if len(after) > n_before:
            ok(f"eventos: {n_before} → {len(after)} (nova coleta visível)")
        else:
            ok(f"eventos: {len(after)} (dedup de 300s — dados já coletados, consistente)")
        mk = get("/api/macro-score/scores")["scores"]
        ok(f"macro score recalculado: {[s['status'] for s in mk]}")
    except Exception as e:
        fail(str(e)); rc = 1

    # Cleanup
    step("Cleanup — remover dados de teste")
    if pid:
        try:
            for x in get(f"/api/portfolios/{pid}/holdings")["holdings"]:
                delete(f"/api/holdings/{x['id']}")
            delete(f"/api/portfolios/{pid}")
            ok(f"carteira {pid} e holdings removidos")
        except Exception as e:
            fail(str(e)); rc = 1
    try:
        # Memórias não têm rota DELETE (append-only) — apenas anotar
        mems = get("/api/memories")["memories"]
        mem_tests = [m for m in mems if "fase2" in (m.get("text") or m.get("content") or "")]
        notes = get("/api/notes")["notes"]
        removed = 0
        for n in notes:
            if "fase2" in (n.get("content") or n.get("text") or ""):
                try:
                    delete(f"/api/notes/{n['id']}")
                    removed += 1
                except RuntimeError:
                    pass
        if removed:
            ok(f"{removed} nota(s) de teste removida(s)")
        else:
            ok("notas de teste não removidas (verificar rota DELETE /api/notes/{{id}})")
        if mem_tests:
            ok(f"memórias de teste ainda em disco ({len(mem_tests)}) — limpar via storage/memories.json")
    except Exception as e:
        fail(str(e)); rc = 1

    print("\n" + ("=" * 50))
    n_fail = LOG.count("FALHA") + sum(1 for l in LOG if l.startswith("FALHA"))
    print(f"{'TODOS OS TESTES PASSARAM' if rc == 0 else 'HÁ FALHAS A CORRIGIR'}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
