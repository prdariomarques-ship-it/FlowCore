"""The office's investment policy — one per office (fase 0 multi-tenant
architecture).

Until fase 0, FlowCore had exactly one installation-wide reference
portfolio, so a single runtime-copy-first file
(~/.flowcore/portfolio_moderate_1m.json) over the bundled default was
the right amount of machinery. Now every office needs its own policy —
this module is the same public API (load/save/reset/is_customized),
office-scoped, backed by storage.client_repo.ClientRepository (SQLite)
instead of a file. A second office signing up can no longer see or
clobber the first office's policy just by both being "the one install."

`current_allocation` behaves exactly as it did before: no office has one
until someone sets it via save_reference_portfolio() — never guessed or
backfilled.
"""

from __future__ import annotations

from typing import Any

from storage.client_repo import ClientRepository


async def is_customized(office_id: str) -> bool:
    return await ClientRepository().is_policy_customized(office_id)


async def load_reference_portfolio(office_id: str) -> dict[str, Any]:
    return await ClientRepository().get_office_policy(office_id)


async def save_reference_portfolio(office_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    return await ClientRepository().save_office_policy(office_id, updates)


async def reset_reference_portfolio(office_id: str) -> dict[str, Any]:
    return await ClientRepository().reset_office_policy(office_id)
