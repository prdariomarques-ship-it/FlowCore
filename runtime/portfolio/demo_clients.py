"""27 example client portfolios — per-office, explicitly fictitious,
explicitly editable seed data (fase 0 multi-tenant architecture).

Same public API this module had before fase 0
(load_demo_clients/save_demo_client/reset_demo_clients), now office-
scoped and backed by storage.client_repo.ClientRepository (SQLite)
instead of a single installation-wide ~/.flowcore/demo_clients.json.

Critically, this module no longer decides WHETHER an office gets demo
clients — that's a one-time decision made at office creation
(ClientRepository.seed_office(office_id, with_demo_clients=...), wired
from the signup/bootstrap flow). Only the one bootstrap "FlowCore Demo"
office is seeded with the 27 examples; every office created by a real
signup starts with zero clients — a real paying customer's account must
never show fabricated clients. This module just reads/edits/resets
whatever an office already has.
"""

from __future__ import annotations

from typing import Any

from storage.client_repo import ClientRepository


async def load_demo_clients(office_id: str) -> list[dict[str, Any]]:
    return await ClientRepository().list_clients(office_id)


async def save_demo_client(office_id: str, client_id: str, current_allocation: dict[str, float]) -> dict[str, Any]:
    return await ClientRepository().save_client_allocation(office_id, client_id, current_allocation)


async def reset_demo_clients(office_id: str) -> list[dict[str, Any]]:
    return await ClientRepository().reset_demo_clients(office_id)
