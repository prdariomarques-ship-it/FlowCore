"""FlowCore Storage — PortfolioRepository.

Sprint 21, Phase 1 of the Wealth Copilot vision — the Portfolio Domain.
Mirrors FlowRepository/EventRepository's shape: async-only, backed by
aiosqlite, same database file via storage.database.get_db_path().

Three tables:
- portfolios: a named container (e.g. "Corretora XP", "Aposentadoria") —
  multi-portfolio from the start, confirmed with the user.
- holdings: quantity/average_cost the user actually owns, belongs to one
  portfolio. Market value is NOT stored here — it's a live-computed value
  (current price x quantity), same "don't persist what can be recomputed
  fresh" philosophy already used for the Integration Dashboard and
  Observer Framework. See runtime/portfolio/valuation.py.
- assets: canonical, symbol-keyed classification data shared across every
  holding that references it (no duplication). Hard columns only for what
  yfinance can actually answer (name/asset_class/country/currency/sector/
  industry); everything else the user listed (theme, duration, credit
  quality, liquidity, income generation, inflation/currency protection,
  risk attributes) lives in one flexible `attributes` JSON column,
  populated manually via tag_asset() — never fabricated. Correlation
  metadata is deliberately NOT a column here at all: it's an inherently
  pairwise/portfolio-level computed property, not a static per-asset
  attribute, and belongs to whichever future phase actually computes it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite

from storage.database import get_db_path


class PortfolioRepository:
    """Async repository for the `portfolios`, `holdings`, and `assets` tables."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or get_db_path()
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    # ── Schema ──────────────────────────────────────────────────────────────

    async def ensure_tables(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS portfolios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS holdings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    portfolio_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    average_cost REAL NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'USD',
                    source TEXT NOT NULL DEFAULT 'manual',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS assets (
                    symbol TEXT PRIMARY KEY,
                    name TEXT,
                    asset_class TEXT,
                    country TEXT,
                    currency TEXT,
                    sector TEXT,
                    industry TEXT,
                    attributes TEXT NOT NULL DEFAULT '{}',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_holdings_portfolio ON holdings(portfolio_id)")
            await db.commit()

    # ── Portfolios ──────────────────────────────────────────────────────────

    async def create_portfolio(self, name: str) -> int:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("INSERT INTO portfolios (name) VALUES (?)", (name,))
            await db.commit()
            return cursor.lastrowid

    async def list_portfolios(self) -> list[dict[str, Any]]:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("SELECT id, name, created_at FROM portfolios ORDER BY created_at DESC, id DESC")
            rows = await cursor.fetchall()
            return [{"id": r[0], "name": r[1], "created_at": r[2]} for r in rows]

    async def get_portfolio(self, portfolio_id: int) -> dict[str, Any] | None:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("SELECT id, name, created_at FROM portfolios WHERE id = ?", (portfolio_id,))
            row = await cursor.fetchone()
            if not row:
                return None
            return {"id": row[0], "name": row[1], "created_at": row[2]}

    async def delete_portfolio(self, portfolio_id: int) -> bool:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM holdings WHERE portfolio_id = ?", (portfolio_id,))
            cursor = await db.execute("DELETE FROM portfolios WHERE id = ?", (portfolio_id,))
            await db.commit()
            return cursor.rowcount > 0

    # ── Holdings ────────────────────────────────────────────────────────────

    async def create_holding(
        self,
        portfolio_id: int,
        symbol: str,
        quantity: float,
        average_cost: float,
        currency: str = "USD",
        source: str = "manual",
    ) -> int:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """INSERT INTO holdings (portfolio_id, symbol, quantity, average_cost, currency, source)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (portfolio_id, symbol.upper(), quantity, average_cost, currency, source),
            )
            await db.commit()
            return cursor.lastrowid

    async def list_holdings(self, portfolio_id: int) -> list[dict[str, Any]]:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """SELECT id, portfolio_id, symbol, quantity, average_cost, currency, source, created_at, updated_at
                   FROM holdings WHERE portfolio_id = ? ORDER BY created_at DESC, id DESC""",
                (portfolio_id,),
            )
            rows = await cursor.fetchall()
            return [self._row_to_holding(r) for r in rows]

    async def get_holding(self, holding_id: int) -> dict[str, Any] | None:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """SELECT id, portfolio_id, symbol, quantity, average_cost, currency, source, created_at, updated_at
                   FROM holdings WHERE id = ?""",
                (holding_id,),
            )
            row = await cursor.fetchone()
            return self._row_to_holding(row) if row else None

    async def update_holding(
        self, holding_id: int, quantity: float | None = None, average_cost: float | None = None
    ) -> bool:
        await self.ensure_tables()
        fields, params = [], []
        if quantity is not None:
            fields.append("quantity = ?")
            params.append(quantity)
        if average_cost is not None:
            fields.append("average_cost = ?")
            params.append(average_cost)
        if not fields:
            return False
        fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(holding_id)
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(f"UPDATE holdings SET {', '.join(fields)} WHERE id = ?", params)
            await db.commit()
            return cursor.rowcount > 0

    async def delete_holding(self, holding_id: int) -> bool:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("DELETE FROM holdings WHERE id = ?", (holding_id,))
            await db.commit()
            return cursor.rowcount > 0

    @staticmethod
    def _row_to_holding(row: tuple) -> dict[str, Any]:
        return {
            "id": row[0],
            "portfolio_id": row[1],
            "symbol": row[2],
            "quantity": row[3],
            "average_cost": row[4],
            "currency": row[5],
            "source": row[6],
            "created_at": row[7],
            "updated_at": row[8],
        }

    # ── Assets ──────────────────────────────────────────────────────────────

    async def upsert_asset(
        self,
        symbol: str,
        name: str | None = None,
        asset_class: str | None = None,
        country: str | None = None,
        currency: str | None = None,
        sector: str | None = None,
        industry: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Insert or merge-update an asset. Only non-None fields overwrite
        existing values; `attributes` is merged (not replaced) with whatever
        is already stored, so tagging one attribute never clobbers others."""
        await self.ensure_tables()
        existing = await self.get_asset(symbol)
        merged_attrs = dict(existing["attributes"]) if existing else {}
        if attributes:
            merged_attrs.update(attributes)

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO assets
                   (symbol, name, asset_class, country, currency, sector, industry, attributes, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(symbol) DO UPDATE SET
                       name = COALESCE(excluded.name, assets.name),
                       asset_class = COALESCE(excluded.asset_class, assets.asset_class),
                       country = COALESCE(excluded.country, assets.country),
                       currency = COALESCE(excluded.currency, assets.currency),
                       sector = COALESCE(excluded.sector, assets.sector),
                       industry = COALESCE(excluded.industry, assets.industry),
                       attributes = excluded.attributes,
                       updated_at = CURRENT_TIMESTAMP""",
                (symbol.upper(), name, asset_class, country, currency, sector, industry, json.dumps(merged_attrs)),
            )
            await db.commit()

    async def get_asset(self, symbol: str) -> dict[str, Any] | None:
        await self.ensure_tables()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """SELECT symbol, name, asset_class, country, currency, sector, industry, attributes, updated_at
                   FROM assets WHERE symbol = ?""",
                (symbol.upper(),),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                "symbol": row[0],
                "name": row[1],
                "asset_class": row[2],
                "country": row[3],
                "currency": row[4],
                "sector": row[5],
                "industry": row[6],
                "attributes": json.loads(row[7]),
                "updated_at": row[8],
            }
