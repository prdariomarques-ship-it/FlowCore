"""Smoke test for the market_intelligence expansion (all real data)."""

from runtime.market_intelligence.yield_curve import build_yield_curve
from runtime.market_intelligence.fx_analysis import analyze_fx
from runtime.market_intelligence.asset_classes import analyze_asset_classes
from runtime.market_intelligence.alerts import evaluate_alerts, list_alerts
from runtime.market_intelligence.briefing import build_briefing

print("=== CURVA ===")
print(build_yield_curve().to_dict())
print("=== FX ===")
print(analyze_fx())
print("=== CLASSES ===")
c = analyze_asset_classes()
print({k: len(v["sources"]) for k, v in c["classes"].items()})
print("=== ALERTS ===")
print(evaluate_alerts(db_path="/tmp/test_alerts.db"))
print(list_alerts(db_path="/tmp/test_alerts.db"))
print("=== BRIEFING ===")
print(build_briefing())
