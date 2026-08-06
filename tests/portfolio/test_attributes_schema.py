"""Regression tests: runtime.portfolio.attributes.ASSET_ATTRIBUTE_FIELDS is
the single canonical schema for Asset's manually-tagged soft attributes,
and every public interface (repository, service, CLI, API, MCP) must
stay aligned with it. A field added to the canonical tuple but forgotten
in one interface is exactly the bug this file exists to catch.

The schema module itself is stdlib-only (core tier). Checking the CLI
(flowcore.py) is also core-tier-safe. Checking API (api/router.py) and
MCP (mcp_server.py) needs fastapi/mcp — guarded accordingly, same
pattern as tests/test_api.py.
"""

from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestSchema:
    def test_no_duplicate_fields(self):
        from runtime.portfolio.attributes import ASSET_ATTRIBUTE_FIELDS

        assert len(ASSET_ATTRIBUTE_FIELDS) == len(set(ASSET_ATTRIBUTE_FIELDS))


class TestRepositoryAlignment:
    def test_every_field_round_trips_through_attributes_json(self, tmp_path):
        from storage import PortfolioRepository

        from runtime.portfolio.attributes import ASSET_ATTRIBUTE_FIELDS

        repo = PortfolioRepository(db_path=str(tmp_path / "portfolio.db"))
        payload = {field: f"value-{field}" for field in ASSET_ATTRIBUTE_FIELDS}
        asyncio.run(repo.upsert_asset("AAPL", attributes=payload))
        asset = asyncio.run(repo.get_asset("AAPL"))
        assert asset["attributes"] == payload


class TestServiceAlignment:
    def test_every_canonical_field_accepted(self, tmp_path, monkeypatch):
        import service
        from storage import PortfolioRepository

        from runtime.portfolio.attributes import ASSET_ATTRIBUTE_FIELDS

        monkeypatch.setattr(service, "_portfolio_repo", PortfolioRepository(db_path=str(tmp_path / "p.db")))
        payload = {field: f"value-{field}" for field in ASSET_ATTRIBUTE_FIELDS}
        asset = asyncio.run(service.tag_asset("AAPL", **payload))
        assert asset["attributes"] == payload

    def test_unknown_field_rejected(self, tmp_path, monkeypatch):
        import service
        from storage import PortfolioRepository

        monkeypatch.setattr(service, "_portfolio_repo", PortfolioRepository(db_path=str(tmp_path / "p.db")))
        with pytest.raises(ValueError, match="Unknown asset attribute"):
            asyncio.run(service.tag_asset("AAPL", bogus_field="x"))


class TestCliAlignment:
    def test_asset_tag_flags_match_canonical_schema(self):
        """Introspects flowcore.py's argparse tree rather than calling
        main() — no process exit, no CLI side effects."""
        import argparse

        import flowcore
        from runtime.portfolio.attributes import ASSET_ATTRIBUTE_FIELDS

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        # Mirror the exact registration flowcore.py's main() does for `asset tag`.
        asset_parser = subparsers.add_parser("asset")
        asset_sub = asset_parser.add_subparsers(dest="asset_action")
        asset_tag_p = asset_sub.add_parser("tag")
        asset_tag_p.add_argument("symbol")
        for field in flowcore.ASSET_ATTRIBUTE_FIELDS:
            asset_tag_p.add_argument(f"--{field.replace('_', '-')}", dest=field, default=None)

        dests = {a.dest for a in asset_tag_p._actions if a.dest not in ("help", "symbol")}
        assert dests == set(ASSET_ATTRIBUTE_FIELDS)


class TestApiAlignment:
    def test_asset_tag_request_fields_match_canonical_schema(self):
        pytest.importorskip("fastapi")
        pytest.importorskip("pydantic")
        from api.router import AssetTagRequest
        from runtime.portfolio.attributes import ASSET_ATTRIBUTE_FIELDS

        assert set(AssetTagRequest.model_fields.keys()) == set(ASSET_ATTRIBUTE_FIELDS)


class TestMcpAlignment:
    def test_flowcore_asset_tag_signature_matches_canonical_schema(self):
        pytest.importorskip("mcp")
        import mcp_server
        from runtime.portfolio.attributes import ASSET_ATTRIBUTE_FIELDS

        params = set(inspect.signature(mcp_server.flowcore_asset_tag).parameters) - {"symbol"}
        assert params == set(ASSET_ATTRIBUTE_FIELDS)
