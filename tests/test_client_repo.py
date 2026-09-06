"""Tests for storage/client_repo.py — office_policies + clients (fase 0c).

Same asyncio.run() convention as tests/test_flow_repo.py /
tests/test_tenant_repo.py — no pytest-asyncio dependency in this project.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _repo(tmp_path: Path):
    from storage.client_repo import ClientRepository

    return ClientRepository(db_path=str(tmp_path / "clients_test.db"))


class TestOfficePolicySeeding:
    def test_seeded_office_gets_the_real_bundled_policy(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            await repo.seed_office("office-a", with_demo_clients=False)
            return await repo.get_office_policy("office-a")

        policy = asyncio.run(scenario())
        assert policy["id"] == "moderate-ia-1m"
        assert policy["target_allocation"]
        assert policy["sleeve_limits"]

    def test_unseeded_office_falls_back_without_crashing(self, tmp_path):
        policy = asyncio.run(_repo(tmp_path).get_office_policy("never-seeded"))
        assert policy["target_allocation"] == []


class TestOfficePolicyEditing:
    def test_save_merges_and_marks_customized(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            await repo.seed_office("office-a", with_demo_clients=False)
            updated = await repo.save_office_policy("office-a", {"name": "Política Editada"})
            customized = await repo.is_policy_customized("office-a")
            return updated, customized

        updated, customized = asyncio.run(scenario())
        assert updated["name"] == "Política Editada"
        assert customized is True

    def test_reset_reverts_and_clears_customized_flag(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            await repo.seed_office("office-a", with_demo_clients=False)
            await repo.save_office_policy("office-a", {"name": "Política Editada"})
            reset = await repo.reset_office_policy("office-a")
            customized = await repo.is_policy_customized("office-a")
            return reset, customized

        reset, customized = asyncio.run(scenario())
        assert reset["name"] != "Política Editada"
        assert customized is False


class TestDemoClientSeeding:
    def test_bootstrap_office_gets_27_demo_clients(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            await repo.seed_office("demo-office", with_demo_clients=True)
            return await repo.list_clients("demo-office")

        clients = asyncio.run(scenario())
        assert len(clients) == 27
        assert all(c["is_demo"] for c in clients)

    def test_real_signup_office_gets_zero_clients(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            await repo.seed_office("real-office", with_demo_clients=False)
            return await repo.list_clients("real-office")

        assert asyncio.run(scenario()) == []


class TestClientEditingAndTenantIsolation:
    def test_edit_persists_and_merges(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            await repo.seed_office("office-a", with_demo_clients=True)
            clients = await repo.list_clients("office-a")
            client_id = clients[0]["id"]
            updated = await repo.save_client_allocation("office-a", client_id, {"ai_theme": 9.0})
            return updated

        updated = asyncio.run(scenario())
        assert updated["current_allocation"]["ai_theme"] == 9.0
        assert "__sleeve__:renda_fixa_total" in updated["current_allocation"]  # other fields untouched

    def test_cannot_edit_another_offices_client(self, tmp_path):
        """The core tenant-isolation guarantee: even with the exact right
        client id, editing from the wrong office_id must fail, never
        silently succeed or leak the other office's data."""
        async def scenario():
            repo = _repo(tmp_path)
            await repo.seed_office("office-a", with_demo_clients=True)
            await repo.seed_office("office-b", with_demo_clients=False)
            client_id = (await repo.list_clients("office-a"))[0]["id"]
            try:
                await repo.save_client_allocation("office-b", client_id, {"ai_theme": 99.0})
                return "no_error"
            except KeyError:
                return "key_error"

        assert asyncio.run(scenario()) == "key_error"

    def test_editing_a_client_in_one_office_never_touches_the_same_id_in_another(self, tmp_path):
        """Two independently-seeded offices reuse the same template client
        ids (e.g. "demo-client-01") — the composite (office_id, id) primary
        key is what actually keeps them isolated, not distinct ids. Prove
        editing one never bleeds into the other."""
        async def scenario():
            repo = _repo(tmp_path)
            await repo.seed_office("office-a", with_demo_clients=True)
            await repo.seed_office("office-b", with_demo_clients=True)
            client_id = (await repo.list_clients("office-a"))[0]["id"]
            assert client_id == (await repo.list_clients("office-b"))[0]["id"]  # same template id, different offices

            await repo.save_client_allocation("office-a", client_id, {"ai_theme": 42.0})
            client_a = await repo.get_client("office-a", client_id)
            client_b = await repo.get_client("office-b", client_id)
            return client_a, client_b

        client_a, client_b = asyncio.run(scenario())
        assert client_a["current_allocation"]["ai_theme"] == 42.0
        assert client_b["current_allocation"]["ai_theme"] != 42.0

    def test_reset_demo_clients_reverts_edits(self, tmp_path):
        async def scenario():
            repo = _repo(tmp_path)
            await repo.seed_office("office-a", with_demo_clients=True)
            client_id = (await repo.list_clients("office-a"))[0]["id"]
            original = (await repo.get_client("office-a", client_id))["current_allocation"]
            await repo.save_client_allocation("office-a", client_id, {"ai_theme": 999.0})
            await repo.reset_demo_clients("office-a")
            reverted = await repo.get_client("office-a", client_id)
            return original, reverted["current_allocation"]

        original, reverted = asyncio.run(scenario())
        assert original == reverted
