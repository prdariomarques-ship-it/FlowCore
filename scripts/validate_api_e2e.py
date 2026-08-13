#!/usr/bin/env python3
"""Validação E2E dos endpoints REST do FlowCore (unit+integração, sem servidor).
Usa FastAPI TestClient contra o app construído em service.py, com o banco real.
"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from api.router import create_app  # noqa: E402 — constrói o app FastAPI
from fastapi.testclient import TestClient

client = TestClient(create_app())

PATHS = [
    ("/api/portfolios", "list portfolios"),
    ("/api/portfolios/1/summary", "portfolio summary"),
    ("/api/portfolios/1/exposure", "exposure full"),
    ("/api/portfolios/1/exposure/inflation_protection", "exposure inflation_protection"),
    ("/api/portfolios/1/concentration", "concentration"),
    ("/api/portfolios/1/impact", "impact"),
    ("/api/portfolios/1/recommendations", "recommendations"),
    ("/api/portfolios/1/decision", "decision"),
    ("/api/portfolios/1/decision/queue", "decision queue"),
    ("/api/portfolios/1/decision/score", "decision score"),
    ("/api/portfolios/1/reason-chain", "reason chain"),
    ("/api/observer/registry", "observer registry"),
    ("/api/observer/events", "observer events"),
    ("/api/observer/health", "observer health (rede)"),
    ("/api/macro-score/dimensions", "macro dimensions"),
    ("/api/macro-score/scores", "macro scores"),
    ("/api/integrations/status", "integrations status"),
    ("/api/status", "system status"),
]

fail = 0
for path, label in PATHS:
    try:
        r = client.get(path)
        body = str(r.json())[:100].replace("\n", " ")
        print(f"{'OK  ' if r.status_code < 400 else 'FAIL'} {r.status_code}  {path:<50} {label:<28} {body}")
        if r.status_code >= 400:
            fail += 1
    except Exception as e:
        print(f"ERR  {path:<50} {label:<28} {type(e).__name__}: {e}")
        fail += 1
print(f"\n{len(PATHS) - fail}/{len(PATHS)} endpoints OK")
sys.exit(0 if fail == 0 else 1)
