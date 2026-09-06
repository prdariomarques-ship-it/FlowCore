"""The FlowCore reference (model) portfolio — single source of truth.

There is exactly one allocation-limit policy in FlowCore today:
config/portfolio_moderate_1m.json (target_allocation + sleeve_limits +
review_policy). It ships bundled with the repo, read-only.

To let it be customized without a redeploy, a *runtime copy* at
~/.flowcore/portfolio_moderate_1m.json takes precedence when present —
the same two-tier convention already used for ai.json/outlook.json
(api/dashboard_routes.py's _read_json). This module is the single loader
for that policy: previously api/dashboard_routes.py and
agents/compliance_agent.py each read it independently, and the agent's
copy only knew about the bundled file — an editor writing the runtime
copy had no effect on ComplianceAgent's evaluation. Both now delegate
here.

`current_allocation` (symbol/id -> current weight %) is the piece the
compliance MVP was missing entirely: nothing in FlowCore persisted a
live position for this portfolio, so ComplianceAgent always reported
SEM_POSICAO_ATUAL. It is now a normal, editable field on this same
object — still never guessed or backfilled, just no longer permanently
absent once someone sets it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DATA_DIR = Path.home() / ".flowcore"
_BUNDLED_DEFAULT = Path(__file__).resolve().parents[2] / "config" / "portfolio_moderate_1m.json"
_RUNTIME_COPY = _DATA_DIR / "portfolio_moderate_1m.json"

_FALLBACK: dict[str, Any] = {
    "id": "moderate-ia-1m",
    "name": "Carteira Moderada — R$ 1 milhão",
    "reference_value": 1000000,
    "target_allocation": [],
    "sleeve_limits": {},
    "review_policy": {},
    "current_allocation": {},
}


def _read(path: Path) -> dict[str, Any] | None:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError):
        pass
    return None


def is_customized() -> bool:
    """True when a runtime copy exists — i.e. someone has edited the
    reference portfolio away from the bundled default."""
    return _RUNTIME_COPY.exists()


def load_reference_portfolio() -> dict[str, Any]:
    """Runtime copy first, then the bundled default, then a minimal
    in-memory fallback if even the bundled file is unreadable."""
    for path in (_RUNTIME_COPY, _BUNDLED_DEFAULT):
        data = _read(path)
        if data is not None:
            return {**_FALLBACK, **data}
    return dict(_FALLBACK)


def save_reference_portfolio(updates: dict[str, Any]) -> dict[str, Any]:
    """Merge `updates` onto the current reference portfolio and persist
    to the runtime copy. Never touches the bundled default — editing
    always creates/updates ~/.flowcore/portfolio_moderate_1m.json, so the
    versioned config stays a clean, restorable baseline."""
    current = load_reference_portfolio()
    current.update({k: v for k, v in updates.items() if v is not None})
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _RUNTIME_COPY.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
    return current


def reset_reference_portfolio() -> dict[str, Any]:
    """Discard the runtime copy, reverting to the bundled default."""
    _RUNTIME_COPY.unlink(missing_ok=True)
    return load_reference_portfolio()
