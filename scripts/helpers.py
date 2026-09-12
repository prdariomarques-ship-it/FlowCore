"""FlowCore Helper Scripts — shared utilities.

This module contains utilities used by the CLI scripts (doctor, repair, etc).
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path


def is_termux() -> bool:
    """Check if running inside Termux."""
    return bool(os.environ.get("PREFIX"))


def is_android() -> bool:
    """Check if running on Android."""
    return is_termux() or os.path.exists("/system/bin/app_process")


def get_python_info() -> dict:
    """Return Python version info."""
    return {
        "version": sys.version.split()[0],
        "major": sys.version_info.major,
        "minor": sys.version_info.minor,
        "platform": platform.system(),
        "arch": platform.machine(),
        "implementation": platform.python_implementation(),
    }


def get_project_root() -> Path:
    """Return the project root."""
    return Path(__file__).resolve().parent.parent


def ensure_dirs(root: Path | None = None) -> None:
    """Ensure all required directories exist."""
    root = root or get_project_root()
    for d in ["data", "logs", "backups", "config"]:
        (root / d).mkdir(parents=True, exist_ok=True)
