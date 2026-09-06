"""27 example client portfolios — explicitly fictitious, explicitly
editable demo/seed data, not real clients.

Requested directly by the team to populate the multi-client views
(Alertas de Desenquadramento table, client KPI counts) while FlowCore
has no real multi-client integration yet. Distinct from every other
"never fabricate data" rule elsewhere in this codebase: those rules are
about an agent answering a real question honestly (e.g. ComplianceAgent
never guessing a position). This is deliberately-created placeholder
data, the same category as the bundled reference/model portfolio itself
— every record carries `"demo": true` so nothing downstream can present
it as a real client, and it is fully editable/replaceable exactly like
the reference portfolio (runtime-copy-first over the bundled defaults).

Each demo client has its own `current_allocation` (their actual
position) but shares the one real investment policy FlowCore has
(target_allocation/sleeve_limits from runtime.portfolio.reference) —
mirroring how one advisory firm applies a single model portfolio's
policy across many client accounts with their own drifted positions.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DATA_DIR = Path.home() / ".flowcore"
_BUNDLED_DEFAULT = Path(__file__).resolve().parents[2] / "config" / "demo_clients.json"
_RUNTIME_COPY = _DATA_DIR / "demo_clients.json"


def _read(path: Path) -> list[dict[str, Any]] | None:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
    except (OSError, json.JSONDecodeError):
        pass
    return None


def is_customized() -> bool:
    return _RUNTIME_COPY.exists()


def load_demo_clients() -> list[dict[str, Any]]:
    """Runtime copy first (edits), then the bundled 27 defaults."""
    for path in (_RUNTIME_COPY, _BUNDLED_DEFAULT):
        data = _read(path)
        if data is not None:
            return data
    return []


def save_demo_client(client_id: str, current_allocation: dict[str, float]) -> dict[str, Any]:
    """Merge `current_allocation` onto one demo client's position and
    persist the full list to the runtime copy. Raises KeyError if
    `client_id` doesn't exist."""
    clients = load_demo_clients()
    for client in clients:
        if client.get("id") == client_id:
            client["current_allocation"] = {**client.get("current_allocation", {}), **current_allocation}
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            _RUNTIME_COPY.write_text(json.dumps(clients, indent=2, ensure_ascii=False), encoding="utf-8")
            return client
    raise KeyError(client_id)


def reset_demo_clients() -> list[dict[str, Any]]:
    """Discard all edits, reverting every demo client to the bundled defaults."""
    _RUNTIME_COPY.unlink(missing_ok=True)
    return load_demo_clients()
