"""Generated voices share the upload/record mutation lifecycle (no provider calls)."""
from __future__ import annotations

import asyncio
import hashlib
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def voice_route(request, monkeypatch, tmp_path):
    from novelvideo.api.routes import characters, projects
    from novelvideo import project_config
    from novelvideo.seedance2_i2v.character_voice_storage import (
        character_voice_resource_key, narrator_voice_resource_key, voice_resource_lock,
    )

    kind = request.param
    ctx = SimpleNamespace(output_dir=tmp_path / 'output', state_dir=tmp_path / 'state',
                          project_id='demo', is_home_node=True)
    ctx.output_dir.mkdir()
    generator = AsyncMock(return_value=b'generated-voice')
    body = SimpleNamespace(description='  Warm voice  ', preview_text='Hello')
    if kind == 'character':
        character = SimpleNamespace(name='Alice', reference_audio_path='',
                                    reference_audio_sha256='', reference_audio_updated_at='',
                                    voice_samples_by_age_group={})
        async def update(name, **fields):
            for field, value in fields.items():
                setattr(character, field, value)
        store = SimpleNamespace(get_character=lambda name: character,
                                update_character=AsyncMock(side_effect=update))
        monkeypatch.setattr(characters, '_resolve_character_project', AsyncMock(
            return_value=(ctx, 'owner', 'demo', ctx.output_dir, str(ctx.output_dir), store)))
        monkeypatch.setattr(characters, 'make_static_url_for_context',
                            lambda *args, **kwargs: '/static/voice')
        monkeypatch.setattr(characters, 'generate_voice_design_audio', generator)
        module, persistence = characters, 'persist_character_voice_file'
        key = character_voice_resource_key(project_dir=ctx.output_dir,
                                           character_name='Alice', slot='default')
        def call():
            return characters.generate_character_voice_sample(
                'demo', 'Alice', 'default', body, user={})
        def check():
            target = ctx.output_dir / character.reference_audio_path
            assert target.is_file()
            assert target.read_bytes() == b'generated-voice'
            assert character.reference_audio_sha256 == hashlib.sha256(target.read_bytes()).hexdigest()
            assert character.voice_prompt == 'Warm voice'
            store.update_character.assert_awaited_once()
    else:
        store = SimpleNamespace(get_all_characters=lambda: [])
        monkeypatch.setattr(projects, 'resolve_project_context', AsyncMock(return_value=ctx))
        monkeypatch.setattr(projects, 'make_sqlite_store_for_context', AsyncMock(return_value=store))
        monkeypatch.setattr(projects, '_narrator_voice_payload', lambda *args: {'generated': True})
        monkeypatch.setattr(projects, 'generate_voice_design_audio', generator)
        module, persistence = projects, '_persist_narrator_voice_content'
        key = narrator_voice_resource_key(project_dir=ctx.output_dir, state_dir=ctx.state_dir)
        def call():
            return projects.generate_narrator_voice('demo', body, user={})
        def check():
            saved = project_config.load_narrator_reference_audio_from_state_dir(ctx.state_dir)
            target = ctx.output_dir / saved['path']
            assert target.read_bytes() == b'generated-voice'
            assert saved['sha256'] == hashlib.sha256(target.read_bytes()).hexdigest()
    return SimpleNamespace(module=module, persistence=persistence, call=call, check=check,
                           lock=lambda: voice_resource_lock(key), generator=generator, ctx=ctx)


@pytest.mark.asyncio
@pytest.mark.parametrize('voice_route', ['character', 'narrator'], indirect=True)
async def test_generated_voice_waits_for_existing_resource_lock(voice_route, monkeypatch):
    route = voice_route
    original = getattr(route.module, route.persistence)
    started = threading.Event()
    def persist(**kwargs):
        started.set()
        return original(**kwargs)
    monkeypatch.setattr(route.module, route.persistence, persist)
    async with route.lock():
        task = asyncio.create_task(route.call())
        # Generation is deliberately outside the mutation lock; publication must wait.
        for _ in range(100):
            if route.generator.await_count:
                break
            await asyncio.sleep(0.01)
        assert route.generator.await_count == 1
        assert not started.is_set()
        assert not task.done()
    response = await asyncio.wait_for(task, 3)
    assert response['ok'] is True
    route.check()


@pytest.mark.asyncio
@pytest.mark.parametrize('voice_route', ['character', 'narrator'], indirect=True)
async def test_generated_voice_cancel_finishes_file_and_metadata(voice_route, monkeypatch):
    route = voice_route
    original = getattr(route.module, route.persistence)
    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    main_thread = threading.get_ident()
    def persist(**kwargs):
        assert threading.get_ident() != main_thread
        result = original(**kwargs)
        loop.call_soon_threadsafe(started.set)
        assert release.wait(5)
        return result
    monkeypatch.setattr(route.module, route.persistence, persist)
    task = asyncio.create_task(route.call())
    try:
        await asyncio.wait_for(started.wait(), 3)
        task.cancel('cancel-generated-voice')
        await asyncio.sleep(0)
        assert not task.done()
        assert route.lock().locked()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError, match='cancel-generated-voice'):
        await task
    route.check()
    assert not route.lock().locked()


@pytest.mark.asyncio
@pytest.mark.parametrize('voice_route', ['narrator'], indirect=True)
async def test_generated_narrator_rejects_first_person_before_provider(voice_route, monkeypatch):
    monkeypatch.setattr(voice_route.module, '_effective_narrator_voice_style',
                        lambda ctx: 'first_person')
    response = await voice_route.call()
    assert response['ok'] is False
    voice_route.generator.assert_not_awaited()
    assert not (voice_route.ctx.output_dir / 'assets').exists()
