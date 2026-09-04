"""FlowCore FlowStore — atomic JSON persistence for flows and flow runs."""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from flows.schema import Flow, FlowRun


class FlowStore:
    _MAX_RUNS = 200

    def __init__(
        self,
        path: Path | None = None,
        runs_path: Path | None = None,
    ) -> None:
        base = Path.home() / ".flowcore"
        base.mkdir(exist_ok=True)
        self._flows_file = path or (base / "flows.json")
        self._runs_file = runs_path or (base / "flow_runs.json")

    # ── Flows ─────────────────────────────────────────────────────────────────

    def _load_flows(self) -> dict[str, dict]:
        if not self._flows_file.exists():
            return {}
        try:
            with open(self._flows_file, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return {d["id"]: d for d in data}
            return data
        except Exception as exc:
            logger.error("FlowStore: error loading flows: {}", exc)
            return {}

    def _save_flows(self, flows: dict[str, dict]) -> None:
        tmp = self._flows_file.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(list(flows.values()), f, indent=2, default=str)
            tmp.replace(self._flows_file)
        except Exception as exc:
            logger.error("FlowStore: error saving flows: {}", exc)

    def save_flow(self, flow: Flow) -> None:
        flows = self._load_flows()
        flows[flow.id] = flow.to_dict()
        self._save_flows(flows)

    def get_flow(self, flow_id: str) -> Flow | None:
        d = self._load_flows().get(flow_id)
        return Flow.from_dict(d) if d else None

    def list_flows(self) -> list[Flow]:
        return sorted(
            [Flow.from_dict(d) for d in self._load_flows().values()],
            key=lambda f: f.created_at,
        )

    def delete_flow(self, flow_id: str) -> bool:
        flows = self._load_flows()
        if flow_id not in flows:
            return False
        del flows[flow_id]
        self._save_flows(flows)
        return True

    def count_flows(self) -> int:
        return len(self._load_flows())

    # ── Runs ──────────────────────────────────────────────────────────────────

    def _load_runs(self) -> list[dict]:
        if not self._runs_file.exists():
            return []
        try:
            with open(self._runs_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.error("FlowStore: error loading runs: {}", exc)
            return []

    def _save_runs(self, runs: list[dict]) -> None:
        tmp = self._runs_file.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(runs[-self._MAX_RUNS:], f, indent=2, default=str)
            tmp.replace(self._runs_file)
        except Exception as exc:
            logger.error("FlowStore: error saving runs: {}", exc)

    def save_run(self, run: FlowRun) -> None:
        runs = self._load_runs()
        idx = next((i for i, r in enumerate(runs) if r["id"] == run.id), None)
        if idx is not None:
            runs[idx] = run.to_dict()
        else:
            runs.append(run.to_dict())
        self._save_runs(runs)

    def get_run(self, run_id: str) -> FlowRun | None:
        for d in self._load_runs():
            if d["id"] == run_id:
                return FlowRun.from_dict(d)
        return None

    def list_runs(self, flow_id: str | None = None, limit: int = 50) -> list[FlowRun]:
        runs = self._load_runs()
        if flow_id:
            runs = [r for r in runs if r.get("flow_id") == flow_id]
        return [FlowRun.from_dict(r) for r in runs[-limit:]]
