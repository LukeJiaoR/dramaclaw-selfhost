from __future__ import annotations

import sqlite3

from provider_hub.importer import import_localminidrama
from provider_hub.store import ProviderStore


def service_payload(**overrides):
    data = {
        "service_type": "text",
        "provider": "openai",
        "protocol": "openai",
        "name": "Text service",
        "base_url": "https://example.test/v1",
        "api_key": "secret-value",
        "models": ["upstream-model"],
        "default_model": "upstream-model",
        "is_default": True,
        "is_active": True,
    }
    data.update(overrides)
    return data


def test_resolve_uses_binding_without_internal_alias_mapping(tmp_path):
    store = ProviderStore(tmp_path / "hub.db")
    service = store.save_service(service_payload())
    store.save_binding("text", service.id, "upstream-model")

    target = store.resolve("text", "DC-scene-builder-LLM")

    assert target.service.id == service.id
    assert target.incoming_model == "DC-scene-builder-LLM"
    assert target.upstream_model == "upstream-model"


def test_exact_route_overrides_capability_default(tmp_path):
    store = ProviderStore(tmp_path / "hub.db")
    default = store.save_service(service_payload(name="Default"))
    special = store.save_service(
        service_payload(name="Special", is_default=False, default_model="large-model")
    )
    store.save_binding("text", default.id, "upstream-model")
    store.save_model_route("DC-hermes-LLM", "text", special.id, "large-model")

    target = store.resolve("text", "DC-hermes-LLM")

    assert target.service.id == special.id
    assert target.upstream_model == "large-model"


def test_blank_key_on_update_preserves_existing_secret(tmp_path):
    store = ProviderStore(tmp_path / "hub.db")
    service = store.save_service(service_payload())
    updated = store.save_service(
        service_payload(name="Renamed", api_key=None),
        service.id,
    )
    assert updated.name == "Renamed"
    assert updated.api_key == "secret-value"


def test_localminidrama_import_is_idempotent_and_sets_defaults(tmp_path):
    source = tmp_path / "local.db"
    conn = sqlite3.connect(source)
    conn.executescript(
        """
        CREATE TABLE ai_service_configs (
          id INTEGER PRIMARY KEY, service_type TEXT, provider TEXT,
          api_protocol TEXT, name TEXT, base_url TEXT, api_key TEXT,
          model TEXT, default_model TEXT, endpoint TEXT, query_endpoint TEXT,
          priority INTEGER, is_default INTEGER, is_active INTEGER,
          settings TEXT, deleted_at TEXT
        );
        INSERT INTO ai_service_configs VALUES (
          1,'tts','xiaomi','','MiMo','https://api.xiaomimimo.com/v1','key',
          '["mimo-v2.5-tts"]','mimo-v2.5-tts','','',0,1,1,
          '{"voice_id":"mimo_default"}',NULL
        );
        """
    )
    conn.commit()
    conn.close()
    store = ProviderStore(tmp_path / "hub.db")

    first = import_localminidrama(source, store, rewrite_localhost=False)
    second = import_localminidrama(source, store, rewrite_localhost=False)

    assert first == {"created": 1, "updated": 0, "total": 1}
    assert second == {"created": 0, "updated": 1, "total": 1}
    assert len(store.list_services()) == 1
    assert store.list_services()[0].protocol == "mimo_chat_audio"
    assert store.list_bindings()["tts"]["model"] == "mimo-v2.5-tts"
