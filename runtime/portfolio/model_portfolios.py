"""The firm's four model reference portfolios (conservador/moderado/
arrojado/agressivo) -- static, bundled comparison policies for the
dashboard's "Risco da Carteira Agregada" card, distinct from an office's
own live policy (runtime/portfolio/reference.py, one per office,
customizable, backed by SQLite).

These are read-only: there is no per-office customization or
current_allocation for a model portfolio -- they exist purely so an
advisor can compare "what does an arrojado client's target allocation
look like" without that being tied to any specific client or office.
Real target-allocation weights (config/portfolio_*_1m.json), not
fabricated at request time.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"

MODEL_PROFILES: dict[str, Path] = {
    "conservador": _CONFIG_DIR / "portfolio_conservative_1m.json",
    "moderado": _CONFIG_DIR / "portfolio_moderate_1m.json",
    "arrojado": _CONFIG_DIR / "portfolio_bold_1m.json",
    "agressivo": _CONFIG_DIR / "portfolio_aggressive_1m.json",
}


def load_model_portfolio(profile: str) -> dict[str, Any] | None:
    """None for an unknown profile name -- callers report that honestly
    rather than silently substituting a different profile's policy."""
    path = MODEL_PROFILES.get(profile)
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))
