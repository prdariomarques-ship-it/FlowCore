"""FlowCore Storage — database path resolution.

Single source of truth for the SQLite path.  All repositories use this.
"""

from __future__ import annotations

from config.loader import get_config

_DEFAULT_URL = "sqlite+aiosqlite:///data/flowcore.db"


def get_db_path() -> str:
    """Return the resolved filesystem path to the SQLite database."""
    cfg = get_config()
    url: str = cfg.get("database", {}).get("url", _DEFAULT_URL)
    return url.replace("sqlite+aiosqlite:///", "")
