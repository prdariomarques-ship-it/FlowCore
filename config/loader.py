"""FlowCore configuration loader.

Reads ``config/default.yml`` and optionally overlays ``config/local.yml``
(if present).  Environment variables override file values using the
``FLOWCORE__`` prefix (e.g. ``FLOWCORE__API__PORT=9090``).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml

# Termux uses a different home; detect it.
_TERMUX_PREFIX = os.environ.get("PREFIX", "")
_IS_TERMUX = bool(_TERMUX_PREFIX)


def _project_root() -> Path:
    """Return the project root directory.

    On Termux the user typically clones into ``$HOME/FlowCore``.
    The heuristic: walk up from this file until we find ``config/default.yml``.
    """
    current = Path(__file__).resolve().parent  # config/
    root = current.parent  # FlowCore/
    if (root / "config" / "default.yml").exists():
        return root
    # Fallback: use CWD if it contains the structure
    cwd = Path.cwd()
    if (cwd / "config" / "default.yml").exists():
        return cwd
    return root


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge *overlay* into *base*."""
    merged = base.copy()
    for key, value in overlay.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _env_overrides(cfg: dict, prefix: str = "FLOWCORE") -> dict:
    """Apply environment variable overrides.

    ``FLOWCORE__API__PORT=9090``  →  ``cfg["api"]["port"] = 9090``
    """
    overrides: dict = {}
    prefix_up = prefix.upper() + "__"
    for env_key, env_val in os.environ.items():
        if not env_key.startswith(prefix_up):
            continue
        parts = env_key[len(prefix_up):].lower().split("__")
        target = overrides
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        last = parts[-1]
        # Coerce numeric strings
        if env_val.isdigit():
            target[last] = int(env_val)
        elif env_val.lower() in ("true", "false"):
            target[last] = env_val.lower() == "true"
        else:
            target[last] = env_val
    return overrides


def load_config(root: Path | None = None) -> dict[str, Any]:
    """Load and return the full configuration dictionary."""
    root = root or _project_root()

    # 1. Load default
    default_path = root / "config" / "default.yml"
    if not default_path.exists():
        raise FileNotFoundError(f"Default config not found: {default_path}")
    with open(default_path) as f:
        cfg = yaml.safe_load(f) or {}

    # 2. Overlay local (optional)
    local_path = root / "config" / "local.yml"
    if local_path.exists():
        with open(local_path) as f:
            local = yaml.safe_load(f) or {}
        cfg = _deep_merge(cfg, local)

    # 3. Overlay environment variables
    env_overrides = _env_overrides(cfg)
    if env_overrides:
        cfg = _deep_merge(cfg, env_overrides)

    # 4. Resolve paths relative to project root
    db_url = cfg.get("database", {}).get("url", "")
    if db_url.startswith("sqlite"):
        data_dir = root / cfg.get("runtime", {}).get("data_dir", "data")
        data_dir.mkdir(parents=True, exist_ok=True)
        db_path = data_dir / "flowcore.db"
        cfg["database"]["url"] = f"sqlite+aiosqlite:///{db_path}"

    # 5. Ensure log directory exists
    log_file = cfg.get("logging", {}).get("file", "logs/flowcore.log")
    log_path = root / log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)

    return cfg


# Singleton instance (lazy)
_config: dict[str, Any] | None = None


def get_config() -> dict[str, Any]:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config() -> dict[str, Any]:
    global _config
    _config = load_config()
    return _config
