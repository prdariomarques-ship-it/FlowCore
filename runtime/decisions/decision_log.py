"""DecisionLog -- persistent, auditable record of every decision with
future performance tracking (TradingAgents-style "decision log with
realised return & alpha vs benchmark").

Every decision emitted by the DecisionEngine is appended to
~/.flowcore/decision_log.md (JSONL under ~/.flowcore/decision_log.jsonl
for programmatic access). When the same ticker is re-evaluated, the
module computes the realised return since the decision timestamp and
the alpha against a benchmark (e.g. ^BVSP for BRL positions, ^GSPC for
USD), appending a result verdict to the ledger.

Numbers are code-calculated; narratives stay LLM-assisted.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from runtime.observers.providers.yfinance_provider import fetch_quote as _yf_quote


_SUFFIXES = ("", ".SA", ".MX")


def _fetch_price(symbol: str) -> float | None:
    """Price snapshot with yfinance-first behaviour, trying exchange
    suffixes (e.g. PETR4 -> PETR4.SA) before giving up."""
    # Benchmarks/indices (e.g. ^BVSP) must never receive an exchange suffix.
    if symbol.startswith("^"):
        candidates = [symbol]
    elif not symbol.endswith((".SA", ".MX")):
        candidates = [symbol] + [symbol + s for s in (".SA", ".MX")]
    else:
        candidates = [symbol]
    for variant in candidates:
        try:
            q = _yf_quote(variant)
            price = q.get("price") if isinstance(q, dict) else None
            if price is not None:
                return float(price)
        except Exception:
            continue
    return None

_DECISION_DIR = Path.home() / ".flowcore"
_JSONL = _DECISION_DIR / "decision_log.jsonl"
_MD = _DECISION_DIR / "decision_log.md"

__all__ = ["DecisionLog", "DecisionEntry"]


@dataclass
class DecisionEntry:
    ts: str  # ISO decision timestamp
    portfolio_id: int | None
    symbol: str
    kind: str  # risk | opportunity
    action: str  # reduce | increase | hold | avoid
    confidence: float
    priority: float
    materiality: str
    rationale: str = ""
    regime_snapshot: str = ""
    entry_price: float | None = None  # price at decision time
    benchmark: str | None = None  # e.g. ^BVSP / ^GSPC
    benchmark_price: float | None = None
    resolved: bool = False
    resolution: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return asdict(self)


class DecisionLog:
    """Append-only ledger with automatic alpha tracking."""

    def __init__(self) -> None:
        _DECISION_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def append(self, entry: DecisionEntry) -> DecisionEntry:
        """Append a new decision and snapshot the entry + benchmark prices."""
        entry = self._snapshot_prices(entry)
        line = json.dumps(entry.to_json(), ensure_ascii=False)
        with _JSONL.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        self._sync_markdown(entry)
        return entry

    # ------------------------------------------------------------------
    def entries(self, limit: int = 100, open_only: bool = False) -> list[DecisionEntry]:
        """Read recent ledger entries (newest first)."""
        if not _JSONL.exists():
            return []
        out: list[DecisionEntry] = []
        for line in _JSONL.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if open_only and d.get("resolved"):
                continue
            clean = {k: v for k, v in d.items() if k in DecisionEntry.__dataclass_fields__}
            out.append(DecisionEntry(**clean))
            if len(out) >= limit:
                break
        return out

    # ------------------------------------------------------------------
    def resolve_open(self) -> list[dict]:
        """For every open decision, compute realised return + alpha vs
        benchmark and append a resolution verdict."""
        updated: list[dict] = []
        resolved_lines: list[str] = []
        if not _JSONL.exists():
            return updated
        for line in _JSONL.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if d.get("resolved") or not d.get("entry_price"):
                resolved_lines.append(line)
                continue
            verdict = self._resolve_one(d)
            d.update(verdict)
            d["resolved"] = True
            d["resolved_at"] = datetime.now(UTC).isoformat()
            resolved_lines.append(json.dumps(d, ensure_ascii=False))
            updated.append(d)
        _JSONL.write_text("\n".join(resolved_lines) + "\n", encoding="utf-8")
        return updated

    # ------------------------------------------------------------------
    # internals --------------------------------------------------------
    def _snapshot_prices(self, entry: DecisionEntry) -> DecisionEntry:
        entry.entry_price = _fetch_price(entry.symbol)
        if entry.benchmark:
            entry.benchmark_price = _fetch_price(entry.benchmark)
        return entry

    def _resolve_one(self, d: dict) -> dict:
        """Compute realised return and alpha since the decision."""
        verdict: dict = {"return_pct": None, "benchmark_return_pct": None, "alpha_pct": None}
        cur_px = _fetch_price(d["symbol"])
        entry_px = d.get("entry_price")
        if entry_px and cur_px:
            verdict["return_pct"] = round((cur_px - entry_px) / entry_px * 100, 2)
        if d.get("benchmark") and d.get("benchmark_price"):
            bench_cur = _fetch_price(d["benchmark"])
            if bench_cur and d["benchmark_price"]:
                verdict["benchmark_return_pct"] = round(
                    (bench_cur - d["benchmark_price"]) / d["benchmark_price"] * 100, 2
                )
            if verdict["return_pct"] is not None and verdict["benchmark_return_pct"] is not None:
                verdict["alpha_pct"] = round(
                    verdict["return_pct"] - verdict["benchmark_return_pct"], 2
                )
        return verdict

    # ------------------------------------------------------------------
    def _sync_markdown(self, entry: DecisionEntry) -> None:
        header = "# FlowCore Decision Log\n\nNumbers are code-calculated; narratives are LLM-assisted. Every output is provenance-tracked.\n\n"
        body = _MD.read_text(encoding="utf-8") if _MD.exists() else ""
        if not body.startswith(header):
            body = header + body
        row = (
            f"| {entry.ts[:19]} | {entry.symbol} | {entry.kind} | {entry.action} | "
            f"conf {entry.confidence:.2f} | prio {entry.priority:.1f} | "
            f"mat {entry.materiality} | entry {entry.entry_price} |\n"
        )
        if "| ---" not in body:
            body += "\n| ts | symbol | kind | action | confidence | priority | materiality | entry_price |\n| --- | --- | --- | --- | --- | --- | --- | --- |\n"
        _MD.write_text(body + row, encoding="utf-8")
