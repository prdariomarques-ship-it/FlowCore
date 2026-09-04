"""Tests for storage.portfolio_repo.PortfolioRepository (Sprint 21).

Core tier — aiosqlite is a core dependency, no optional-dependency guard
needed (same as tests/test_event_repo.py).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _repo(tmp_path):
    from storage import PortfolioRepository

    return PortfolioRepository(db_path=str(tmp_path / "portfolio.db"))


class TestEnsureTables:
    def test_idempotent(self, tmp_path):
        repo = _repo(tmp_path)
        asyncio.run(repo.ensure_tables())
        asyncio.run(repo.ensure_tables())  # must not raise


class TestPortfolios:
    def test_create_and_list(self, tmp_path):
        repo = _repo(tmp_path)
        pid = asyncio.run(repo.create_portfolio("Corretora XP"))
        portfolios = asyncio.run(repo.list_portfolios())
        assert len(portfolios) == 1
        assert portfolios[0]["id"] == pid
        assert portfolios[0]["name"] == "Corretora XP"

    def test_get_missing_returns_none(self, tmp_path):
        repo = _repo(tmp_path)
        assert asyncio.run(repo.get_portfolio(999)) is None

    def test_multiple_portfolios(self, tmp_path):
        repo = _repo(tmp_path)
        asyncio.run(repo.create_portfolio("A"))
        asyncio.run(repo.create_portfolio("B"))
        portfolios = asyncio.run(repo.list_portfolios())
        assert {p["name"] for p in portfolios} == {"A", "B"}

    def test_delete_cascades_to_holdings(self, tmp_path):
        repo = _repo(tmp_path)
        pid = asyncio.run(repo.create_portfolio("X"))
        asyncio.run(repo.create_holding(pid, "AAPL", 10, 150.0))
        deleted = asyncio.run(repo.delete_portfolio(pid))
        assert deleted is True
        assert asyncio.run(repo.list_holdings(pid)) == []

    def test_delete_missing_returns_false(self, tmp_path):
        repo = _repo(tmp_path)
        assert asyncio.run(repo.delete_portfolio(999)) is False


class TestHoldings:
    def test_create_and_list(self, tmp_path):
        repo = _repo(tmp_path)
        pid = asyncio.run(repo.create_portfolio("X"))
        hid = asyncio.run(repo.create_holding(pid, "aapl", 10, 150.0, currency="USD"))
        holdings = asyncio.run(repo.list_holdings(pid))
        assert len(holdings) == 1
        assert holdings[0]["id"] == hid
        assert holdings[0]["symbol"] == "AAPL"  # normalized uppercase
        assert holdings[0]["source"] == "manual"

    def test_holdings_scoped_to_portfolio(self, tmp_path):
        repo = _repo(tmp_path)
        p1 = asyncio.run(repo.create_portfolio("A"))
        p2 = asyncio.run(repo.create_portfolio("B"))
        asyncio.run(repo.create_holding(p1, "AAPL", 10, 150.0))
        asyncio.run(repo.create_holding(p2, "MSFT", 5, 300.0))
        assert [h["symbol"] for h in asyncio.run(repo.list_holdings(p1))] == ["AAPL"]
        assert [h["symbol"] for h in asyncio.run(repo.list_holdings(p2))] == ["MSFT"]

    def test_update_quantity_only(self, tmp_path):
        repo = _repo(tmp_path)
        pid = asyncio.run(repo.create_portfolio("X"))
        hid = asyncio.run(repo.create_holding(pid, "AAPL", 10, 150.0))
        updated = asyncio.run(repo.update_holding(hid, quantity=20))
        assert updated is True
        holding = asyncio.run(repo.get_holding(hid))
        assert holding["quantity"] == 20
        assert holding["average_cost"] == 150.0  # untouched

    def test_update_with_no_fields_returns_false(self, tmp_path):
        repo = _repo(tmp_path)
        pid = asyncio.run(repo.create_portfolio("X"))
        hid = asyncio.run(repo.create_holding(pid, "AAPL", 10, 150.0))
        assert asyncio.run(repo.update_holding(hid)) is False

    def test_delete_holding(self, tmp_path):
        repo = _repo(tmp_path)
        pid = asyncio.run(repo.create_portfolio("X"))
        hid = asyncio.run(repo.create_holding(pid, "AAPL", 10, 150.0))
        assert asyncio.run(repo.delete_holding(hid)) is True
        assert asyncio.run(repo.get_holding(hid)) is None

    def test_get_missing_holding_returns_none(self, tmp_path):
        repo = _repo(tmp_path)
        assert asyncio.run(repo.get_holding(999)) is None


class TestAssets:
    def test_upsert_and_get(self, tmp_path):
        repo = _repo(tmp_path)
        asyncio.run(repo.upsert_asset("aapl", name="Apple Inc.", sector="Technology", asset_class="equity"))
        asset = asyncio.run(repo.get_asset("AAPL"))
        assert asset["symbol"] == "AAPL"
        assert asset["name"] == "Apple Inc."
        assert asset["sector"] == "Technology"
        assert asset["attributes"] == {}

    def test_get_missing_returns_none(self, tmp_path):
        repo = _repo(tmp_path)
        assert asyncio.run(repo.get_asset("NOPE")) is None

    def test_upsert_preserves_unset_fields(self, tmp_path):
        repo = _repo(tmp_path)
        asyncio.run(repo.upsert_asset("AAPL", name="Apple Inc.", sector="Technology"))
        asyncio.run(repo.upsert_asset("AAPL", asset_class="equity"))  # doesn't touch name/sector
        asset = asyncio.run(repo.get_asset("AAPL"))
        assert asset["name"] == "Apple Inc."
        assert asset["sector"] == "Technology"
        assert asset["asset_class"] == "equity"

    def test_attributes_merge_not_replace(self, tmp_path):
        repo = _repo(tmp_path)
        asyncio.run(repo.upsert_asset("AAPL", attributes={"theme": "AI"}))
        asyncio.run(repo.upsert_asset("AAPL", attributes={"duration": "n/a"}))
        asset = asyncio.run(repo.get_asset("AAPL"))
        assert asset["attributes"] == {"theme": "AI", "duration": "n/a"}

    def test_attributes_overwrite_same_key(self, tmp_path):
        repo = _repo(tmp_path)
        asyncio.run(repo.upsert_asset("AAPL", attributes={"theme": "AI"}))
        asyncio.run(repo.upsert_asset("AAPL", attributes={"theme": "Semiconductors"}))
        asset = asyncio.run(repo.get_asset("AAPL"))
        assert asset["attributes"] == {"theme": "Semiconductors"}
