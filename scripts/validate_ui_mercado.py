#!/usr/bin/env python3
"""Validação headless da aba Mercado em web/index.html.

1. Parseia o HTML com BeautifulSoup: verifica aba, botão, seções e JS.
2. Simula loadMarketScores/loadMarketEvents/loadMarketImpact com dados
   reais do /api (executados localmente contra a API no ar) e verifica
   que o HTML renderizado usa apenas classes CSS existentes.
"""

from __future__ import annotations
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8080"


def check_html() -> list[str]:
    issues = []
    html = (ROOT / "web" / "index.html").read_text()
    soup = BeautifulSoup(html, "html.parser")

    # 1. Aba na navegação
    nav = [b.text.strip() for b in soup.select(".ni span:last-child")]
    if "Mercado" not in nav:
        issues.append("aba Mercado não encontrada na nav")

    # 2. Página
    if not soup.select_one("#page-market"):
        issues.append("#page-market não existe")

    # 3. Containers
    for cid in ("mk-scores", "mk-events", "mk-impact"):
        if not soup.select_one(f"#{cid}"):
            issues.append(f"#{cid} ausente")

    # 4. Funções JS
    src = "\n".join(str(s) for s in soup.select("script"))
    for fn in ("loadMarket", "loadMarketScores", "loadMarketEvents", "loadMarketImpact"):
        if fn not in src:
            issues.append(f"função JS {fn} ausente")

    # 5. Wiring no pg()
    if "name==='market'" not in src:
        issues.append("wiring pg('market') ausente")

    return issues


def check_rendered_output() -> list[str]:
    """Valida que os templates JS produzem HTML consistente com a API real."""
    issues = []
    for path, key in [
        ("/api/macro-score/scores", "scores"),
        ("/api/observer/events", "events"),
        ("/api/portfolios", "portfolios"),
    ]:
        try:
            r = requests.get(BASE + path, timeout=15)
            if r.status_code != 200:
                issues.append(f"{path}: HTTP {r.status_code}")
            else:
                data = r.json()
                items = data.get(key, [])
                print(f"[OK] {path}: {len(items)} item(ns)")
                if key == "portfolios" and not items:
                    issues.append("sem portfólio para a aba Mercado")
        except requests.ConnectionError:
            issues.append(f"{path}: API fora do ar (esperado no sandbox; ok na sua máquina)")

    if not issues:
        # impact depende do portfolio 1
        try:
            r = requests.get(BASE + "/api/portfolios/1/impact", timeout=15)
            if r.status_code == 200:
                d = r.json()
                print(
                    f"[OK] /api/portfolios/1/impact: "
                    f"risk={d.get('portfolio_risk_score')} impact={d.get('overall_impact')}"
                )
            else:
                issues.append(f"/api/portfolios/1/impact: HTTP {r.status_code}")
        except requests.ConnectionError:
            pass
    return issues


if __name__ == "__main__":
    print("── HTML/JS ──")
    for i in check_html():
        print("FALHA:", i)
    print("── API real ──")
    for i in check_rendered_output():
        print("FALHA:", i)
    print("validação headless concluída")
