"""ExposureEngine — deterministic, weighted classification breakdowns.

Phase 2 of the Wealth Copilot vision (Portfolio Intelligence). Pure
computation over holdings already enriched by service.list_holdings()
(live market_value + asset classification joined in) — no network calls
of its own, core-tier, no new dependency.

One generic compute() grouping function, not one hand-written function
per dimension — adding a new hard-column dimension is a one-line
addition to _HARD_DIMENSIONS + a one-line wrapper method; every soft
attribute (theme, region, growth_profile, ...) is already queryable via
by_attribute() with zero new code, since it reads from the same
canonical ASSET_ATTRIBUTE_FIELDS schema the Portfolio Domain already
maintains.

Deliberately out of scope here (see Sprint 21's architecture review):
correlation (needs historical price data across pairs, not a static
per-asset attribute) and macro exposure — interest rate/inflation/credit/
currency sensitivity (needs holdings mapped to Regime/MacroScore
dimensions, which is Impact Engine territory, Phase 3). Building either
now would be exactly the kind of abstraction with no real consumer yet
that the architecture principles warn against.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime

from runtime.exposure.bucket import ConcentrationReport, ExposureBucket, ExposureReport
from runtime.portfolio.attributes import ASSET_ATTRIBUTE_FIELDS

_HARD_DIMENSIONS = ("asset_class", "sector", "industry", "country", "currency")


class ExposureError(RuntimeError):
    """Raised for an unknown exposure dimension."""


class ExposureEngine:
    def compute(self, holdings: list[dict], group_by: Callable[[dict], str | None], dimension: str) -> ExposureReport:
        """Holdings with no live market_value (failed valuation) are
        excluded from the weighted breakdown but counted in
        unvalued_count — never silently treated as zero. Holdings whose
        group_by(holding) returns None land in an explicit "Unclassified"
        bucket instead of being dropped."""
        valued = [h for h in holdings if h.get("market_value") is not None]
        total = sum(h["market_value"] for h in valued)

        groups: dict[str, list[dict]] = defaultdict(list)
        for h in valued:
            key = group_by(h) or "Unclassified"
            groups[key].append(h)

        buckets = []
        for label, group_holdings in groups.items():
            market_value = sum(h["market_value"] for h in group_holdings)
            buckets.append(
                ExposureBucket(
                    label=label,
                    market_value=market_value,
                    weight_pct=(market_value / total * 100) if total else 0.0,
                    holding_count=len(group_holdings),
                    symbols=[h["symbol"] for h in group_holdings],
                )
            )
        buckets.sort(key=lambda b: b.weight_pct, reverse=True)

        return ExposureReport(
            dimension=dimension,
            total_market_value=total,
            buckets=buckets,
            unvalued_count=len(holdings) - len(valued),
            computed_at=datetime.now(UTC).isoformat(),
        )

    def by_asset_class(self, holdings: list[dict]) -> ExposureReport:
        return self.compute(holdings, lambda h: (h.get("asset") or {}).get("asset_class"), "asset_class")

    def by_sector(self, holdings: list[dict]) -> ExposureReport:
        return self.compute(holdings, lambda h: (h.get("asset") or {}).get("sector"), "sector")

    def by_industry(self, holdings: list[dict]) -> ExposureReport:
        return self.compute(holdings, lambda h: (h.get("asset") or {}).get("industry"), "industry")

    def by_country(self, holdings: list[dict]) -> ExposureReport:
        return self.compute(holdings, lambda h: (h.get("asset") or {}).get("country"), "country")

    def by_currency(self, holdings: list[dict]) -> ExposureReport:
        return self.compute(holdings, lambda h: (h.get("asset") or {}).get("currency"), "currency")

    def by_attribute(self, holdings: list[dict], attribute: str) -> ExposureReport:
        if attribute not in ASSET_ATTRIBUTE_FIELDS:
            raise ExposureError(f"Unknown attribute: {attribute!r}")
        return self.compute(holdings, lambda h: (h.get("asset") or {}).get("attributes", {}).get(attribute), attribute)

    def by_dimension(self, holdings: list[dict], dimension: str) -> ExposureReport:
        """Single entry point for a dimension chosen at runtime (hard
        column or soft attribute) — what service.py's API/CLI/MCP layer
        calls for GET /api/portfolios/{id}/exposure/{dimension}."""
        if dimension in _HARD_DIMENSIONS:
            return getattr(self, f"by_{dimension}")(holdings)
        if dimension in ASSET_ATTRIBUTE_FIELDS:
            return self.by_attribute(holdings, dimension)
        raise ExposureError(f"Unknown exposure dimension: {dimension!r}")

    def full_report(self, holdings: list[dict]) -> dict[str, ExposureReport]:
        """The hard-column dimensions only. Soft attributes are opt-in via
        by_dimension()/by_attribute() — most holdings won't have them
        tagged yet, so including them here by default would mean a
        report that's mostly "Unclassified" noise."""
        return {dim: getattr(self, f"by_{dim}")(holdings) for dim in _HARD_DIMENSIONS}


def compute_concentration(holdings: list[dict]) -> ConcentrationReport:
    """Herfindahl-Hirschman Index (sum of squared weight percentages,
    0-10000 scale — 10000 means a single holding is 100% of the
    portfolio) plus top-1/top-5 weight, all standard deterministic
    arithmetic, no interpretation of what counts as "too concentrated"."""
    valued = [h for h in holdings if h.get("market_value") is not None]
    total = sum(h["market_value"] for h in valued)
    now = datetime.now(UTC).isoformat()
    unvalued_count = len(holdings) - len(valued)

    if not valued or not total:
        return ConcentrationReport(
            total_market_value=0.0,
            top_holding_weight_pct=0.0,
            top_5_weight_pct=0.0,
            hhi=0.0,
            holding_count=len(holdings),
            unvalued_count=unvalued_count,
            computed_at=now,
        )

    weights = sorted((h["market_value"] / total * 100 for h in valued), reverse=True)
    hhi = sum(w * w for w in weights)
    return ConcentrationReport(
        total_market_value=total,
        top_holding_weight_pct=weights[0],
        top_5_weight_pct=sum(weights[:5]),
        hhi=hhi,
        holding_count=len(holdings),
        unvalued_count=unvalued_count,
        computed_at=now,
    )
