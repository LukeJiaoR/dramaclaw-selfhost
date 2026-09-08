from types import SimpleNamespace

import pytest

from novelvideo.cognee.store import CogneeStore


@pytest.mark.asyncio
async def test_episode_asset_ref_scope_uses_episode_prop_menu():
    store = CogneeStore.__new__(CogneeStore)
    store.sqlite_store = SimpleNamespace(list_props=lambda: None)

    async def get_episode_from_graph(_episode_number: int):
        return SimpleNamespace(
            identity_ids=[],
            prop_menu=[SimpleNamespace(prop_id="羊皮笔记本")],
        )

    async def list_characters():
        return []

    store.get_episode_from_graph = get_episode_from_graph
    store.list_characters = list_characters

    _identity_ids, prop_ids = await store._episode_asset_ref_scope(1)

    assert prop_ids == {"羊皮笔记本"}


@pytest.mark.asyncio
async def test_episode_asset_ref_scope_falls_back_to_legacy_global_props():
    store = CogneeStore.__new__(CogneeStore)

    async def get_episode_from_graph(_episode_number: int):
        return SimpleNamespace(identity_ids=[], prop_menu=[])

    async def list_characters():
        return []

    async def list_props():
        return [SimpleNamespace(name="羊皮笔记本")]

    store.get_episode_from_graph = get_episode_from_graph
    store.list_characters = list_characters
    store.sqlite_store = SimpleNamespace(list_props=list_props)

    _identity_ids, prop_ids = await store._episode_asset_ref_scope(1)

    assert prop_ids == {"羊皮笔记本"}
