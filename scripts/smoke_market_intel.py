#!/usr/bin/env python3
"""Smoke test for the Market Intelligence expansion — real data, no mocks.

Exits 0 only when every deterministic module returns sane, non-fabricated
output against live yfinance data. Designed to run on the user's machine
(after applying the branch) exactly like the other validation scripts.
"""
from __future__ import annotations
import sys
import time

sys.path.insert(0, ".")


def banner(title: str) -> None:
    print(f"\n=== {title} ===", flush=True)


def main() -> int:
    fails: list[str] = []
    t0 = time.time()

    # 1. Observer expansion: registry must include the new sources.
    from runtime.observers.registry import registry
    expected = ["ibovespa", "sp500", "nasdaq", "dow", "russell2000",
                "treasury_5y", "treasury_2y", "dxy", "eurostoxx", "dax",
                "ftse", "eurusd", "nikkei", "hangseng", "shanghai", "usdcny",
                "wti", "silver", "copper"]
    missing = [s for s in expected if s not in registry.names()]
    if missing:
        fails.append(f"observers: faltam {missing}")
    banner("1. observers")
    print(f"  total={len(registry.names())} | faltando={missing or 'nenhum'}")

    # 2. Yield curve with shape classification.
    from runtime.market_intelligence.yield_curve import build_yield_curve
    curve = build_yield_curve()
    if curve.state == "insufficient_data":
        fails.append("yield_curve: insufficient_data")
    banner("2. yield curve")
    print(f"  state={curve.state} shape={curve.shape}")
    print(f"  interp={'(nenhuma — dados não sustentam)' if curve.interpretation is None else curve.interpretation[:110]}")

    # 3. Score history.
    from runtime.market_intelligence.score_history import record_scores, score_history
    record_scores([{"dimension": "commodities", "score": 0.42, "status": "scored"},
                   {"dimension": "liquidity", "score": -0.21, "status": "scored"}])
    hist = score_history("commodities")
    latest = hist.get("windows", {}).get("commodities", {}).get("latest")
    banner("3. score history")
    print(f"  latest={latest}")
    if not latest or latest.get("value") is None:
        fails.append("score_history: sem snapshot gravado")

    # 4. Correlation + risk contribution (real closes).
    from runtime.market_intelligence.risk import correlation_matrix, risk_contribution
    corr = correlation_matrix(["^GSPC", "GC=F", "BZ=F", "^TNX", "USDBRL=X"], days=60)
    banner("4. correlation")
    print(f"  symbols={corr['symbols']} dropped={corr['dropped']}")
    if len(corr["symbols"]) < 3:
        fails.append(f"correlation: poucos símbolos ({corr['symbols']})")
    rc = risk_contribution({"^GSPC": 1.0, "GC=F": 0.3, "BZ=F": 0.3, "^TNX": 0.5}, days=60)
    banner("5. risk contribution")
    print(f"  port_vol={rc.get('portfolio_volatility_annualized')} "
          f"analise={'ok' if rc.get('analysis') else rc.get('error')} "
          f"dropped={rc['dropped']}")
    if not rc.get("analysis"):
        fails.append("risk_contribution: sem análise")

    # 5. Rebalancing.
    from runtime.market_intelligence.rebalance import analyze_rebalancing
    reb = analyze_rebalancing(
        [{"symbol": "SGOV", "value": 7000}, {"symbol": "^GSPC", "value": 3000}],
        {"cash_short_duration": 0.5, "equities_index": 0.5})
    banner("6. rebalancing")
    print(f"  buckets={[(b['bucket'], b['deviation_pct']) for b in reb['buckets']]}")
    print(f"  actions={ {k: v['action'] for k, v in reb['actions'].items()} }")
    if reb.get("error"):
        fails.append(f"rebalance: {reb['error']}")

    # 6. News (real Yahoo feeds).
    from runtime.market_intelligence.news import fetch_news
    news = fetch_news(["brazil", "us_equities"], max_per_group=3)
    banner("7. news")
    print(f"  itens={len(news['items'])} | categorias={sorted({i['category'] for i in news['items']})}")
    if not news["items"]:
        fails.append("news: nenhum item")

    elapsed = time.time() - t0
    print(f"\n>>> {len(fails)} falhas em {elapsed:.0f}s")
    for f in fails:
        print(f"  FAIL: {f}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
