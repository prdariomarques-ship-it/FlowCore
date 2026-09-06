"""FlowCore Market Agent — observes market indicators (Wealth Copilot MVP 2).

Reuses runtime.market_intelligence.watchlist.snapshot("default"), which
already fetches Ibovespa, S&P 500, Nasdaq, USD/BRL, Treasuries, DXY, gold,
oil, silver and copper live via yfinance (see
runtime/observers/providers/yfinance_provider.py for the retry/timeout/
cache logic already built for it) — this agent does not talk to yfinance
directly, it classifies what watchlist.py already returns.

DI Jan has no connected source (no B3 futures feed exists in FlowCore
today) and is reported with source="MOCK" per the MVP2 spec's explicit
"não inventar dados; usar MOCK claramente identificado quando a fonte
real ainda não existe" — never blended with the real entries, always
distinguishable by its `source` field.

This agent only OBSERVES and classifies relevance (HIGH/MEDIUM/LOW)
against config/market_thresholds.py. It does not interpret what a move
means for any portfolio — that is IntelligenceEngine's job (MVP2 phase 2).
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from agents.base import BaseAgent
from agents.contracts import MarketMovement, MarketSnapshot
from config.market_thresholds import MARKET_THRESHOLDS

# DI Jan example values — clearly not live data (symbol=None in
# MARKET_THRESHOLDS is the source of truth for "no real feed exists");
# these two numbers exist only so the indicator isn't silently absent
# from the table, exactly as the spec asked for a labeled MOCK fallback.
_DI_MOCK_PREVIOUS = 13.10
_DI_MOCK_CURRENT = 13.15


def _relevance(abs_change: float, high: float, medium: float) -> str:
    if abs_change >= high:
        return "HIGH"
    if abs_change >= medium:
        return "MEDIUM"
    return "LOW"


class MarketAgent(BaseAgent):
    name = "market"
    description = "Observa indicadores de mercado e classifica a relevância de cada movimento"
    version = "0.1.0"

    async def run(self, context: dict | None = None) -> dict[str, Any]:
        # _build_movements() is a plain sync function that calls
        # watchlist.snapshot(), which blocks on ThreadPoolExecutor.as_completed()
        # while it fetches ~9 live quotes. Calling it directly from this
        # async def would run that blocking work on the event loop thread
        # itself, freezing every other concurrent request on this FastAPI
        # process (including fast, unrelated ones like /api/alerts) for as
        # long as the slowest quote takes — the same class of bug already
        # found and fixed once in runtime/market_intelligence/alerts.py.
        # run_in_executor hands it to a worker thread instead.
        loop = asyncio.get_event_loop()
        movements = await loop.run_in_executor(None, self._build_movements)
        relevant = [m for m in movements if m.relevance in ("HIGH", "MEDIUM")]
        market_status = (
            "ALERT" if any(m.relevance == "HIGH" for m in movements)
            else "ATTENTION" if relevant
            else "NORMAL"
        )
        relevant_changes = [
            f"{m.asset} {'subiu' if (m.change or 0) >= 0 else 'caiu'} "
            f"{abs(m.change):.2f}{'pp' if m.unit == 'percentage_points' else '%'}"
            for m in relevant
        ]
        snapshot = MarketSnapshot(
            timestamp=datetime.now(UTC).isoformat(),
            market_status=market_status,
            movements=movements,
            relevant_changes=relevant_changes,
            potential_impacts=[],  # IntelligenceEngine's job, not observed here
        )
        return {"status": "ok", "data": snapshot.to_dict()}

    def _build_movements(self) -> list[MarketMovement]:
        from runtime.market_intelligence.watchlist import snapshot

        live = snapshot("default")
        by_symbol = {item["symbol"]: item for item in live.get("items", [])}

        movements: list[MarketMovement] = []
        for key, cfg in MARKET_THRESHOLDS.items():
            if cfg["symbol"] is None:
                movements.append(self._mock_movement(cfg))
                continue
            item = by_symbol.get(cfg["symbol"])
            movements.append(self._movement_from_watchlist_item(cfg, item))
        return movements

    @staticmethod
    def _mock_movement(cfg: dict) -> MarketMovement:
        change = round(_DI_MOCK_CURRENT - _DI_MOCK_PREVIOUS, 2)
        relevance = _relevance(abs(change), cfg["high"], cfg["medium"])
        return MarketMovement(
            asset=cfg["label"], previous_value=_DI_MOCK_PREVIOUS, current_value=_DI_MOCK_CURRENT,
            change=change, unit=cfg["unit"], relevance=relevance, source="MOCK",
        )

    @staticmethod
    def _movement_from_watchlist_item(cfg: dict, item: dict | None) -> MarketMovement:
        if item is None or item.get("status") != "ok" or item.get("level") is None:
            return MarketMovement(
                asset=cfg["label"], previous_value=None, current_value=None,
                change=None, unit=cfg["unit"], relevance="LOW", source="live",
            )
        current = item["level"]
        delta_pct = item.get("delta_pct_1d")
        if cfg["unit"] == "percent":
            change = delta_pct
            previous = round(current - change, 4) if change is not None else None
        else:
            # percentage_points: watchlist only gives level + %-of-price
            # delta, so back out the previous yield level from that percent
            # move (current / (1 + delta_pct/100) = previous), then the
            # point change is current - previous. Same convention as
            # runtime/market_intelligence/yield_curve.py's own delta calc.
            if delta_pct is None:
                previous = None
                change = None
            else:
                previous = round(current / (1 + delta_pct / 100), 4) if (1 + delta_pct / 100) else None
                change = round(current - previous, 4) if previous is not None else None
        relevance = _relevance(abs(change), cfg["high"], cfg["medium"]) if change is not None else "LOW"
        return MarketMovement(
            asset=cfg["label"], previous_value=previous, current_value=current,
            change=change, unit=cfg["unit"], relevance=relevance, source="live",
        )
