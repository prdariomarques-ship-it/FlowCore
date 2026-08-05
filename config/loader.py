"""FlowCore configuration loader.

Reads config/default.json and optionally overlays config/local.json.
Environment variables override file values using FLOWCORE__ prefix.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_TERMUX_PREFIX = os.environ.get("PREFIX", "")
_IS_TERMUX = bool(_TERMUX_PREFIX)


def _project_root() -> Path:
    """Return project root directory."""
    current = Path(__file__).resolve().parent
    root = current.parent
    if (root / "config" / "default.json").exists():
        return root
    cwd = Path.cwd()
    if (cwd / "config" / "default.json").exists():
        return cwd
    return root


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge overlay into base."""
    merged = base.copy()
    for key, value in overlay.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _env_overrides(cfg: dict, prefix: str = "FLOWCORE") -> dict:
    """Apply environment variable overrides."""
    result = cfg.copy()
    for key, value in os.environ.items():
        if key.startswith(f"{prefix}__"):
            parts = key[len(prefix)+2:].lower().split("__")
            target = result
            for part in parts[:-1]:
                if part not in target:
                    target[part] = {}
                target = target[part]
            target[parts[-1]] = value
    return result


_CONFIG = None


def get_config() -> dict[str, Any]:
    """Get configuration (cached)."""
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG
    _CONFIG = load_config()
    return _CONFIG


def load_config() -> dict[str, Any]:
    """Load configuration from JSON files and environment."""
    root = _project_root()
    
    default_file = root / "config" / "default.json"
    if not default_file.exists():
        raise FileNotFoundError(f"Config not found: {default_file}")
    
    with open(default_file) as f:
        cfg = json.load(f)
    
    local_file = root / "config" / "local.json"
    if local_file.exists():
        with open(local_file) as f:
            local = json.load(f) or {}
        cfg = _deep_merge(cfg, local)
    
    cfg = _env_overrides(cfg)
    return cfg


def reload_config() -> dict[str, Any]:
    """Reload configuration."""
    global _CONFIG
    _CONFIG = None
    return get_config()
