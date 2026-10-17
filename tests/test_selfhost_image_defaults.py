"""Selfhost defaults must survive upstream merges without masking explicit choices."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


_PROBE = """
import json
from types import SimpleNamespace
import dotenv

# This is an environment-only contract: never read a developer's .env or gateway DB.
dotenv.load_dotenv = lambda *args, **kwargs: False
from novelvideo import config
config.get_effective_newapi_gateway_config = lambda: SimpleNamespace(
    api_key="unused-test-key", base_url="https://newapi.invalid/v1"
)
from novelvideo.api import schemas
from novelvideo.freezone import presets, route_helpers, workflow_preflight


def route(value):
    return {key: value.get(key, "") for key in ("provider", "model", "base_url")}


schema_defaults = {
    name: model.model_fields["model"].default
    for name, model in vars(schemas).items()
    if name in (
        "FreezoneScene360Request", "FreezoneCharacterMultiViewRequest",
        "FreezoneTemplateEditRequest", "FreezoneUpscaleRequest",
        "FreezoneOutpaintRequest", "FreezoneRedrawRequest", "FreezoneRelightRequest",
    )
}
try:
    route_helpers.resolve_freezone_image_provider("unsupported")
except Exception as exc:
    strict_status = getattr(exc, "status_code", None)
else:
    strict_status = None
recommended_nodes = [{"id": "image", "node_type": "imageGenNode",
                      "data": {"model": "recommended"}}]
catalog = [
    {"id": key, "ratioOptions": ["9:16"], "resolutionOptions": ["1K"],
     "qualityOptions": ["medium"]}
    for key in ("newapi_gpt_image2", "newapi_nanobanana2", "provider_hub_image")
]
recommendation_blockers = workflow_preflight.resolve_generation_recommendations(
    recommended_nodes, {"imageGenNode": {"ok": True, "data": catalog}}
)
unavailable_nodes = [{"id": "image", "node_type": "imageGenNode",
                      "data": {"model": "recommended"}}]
unavailable_blockers = workflow_preflight.resolve_generation_recommendations(
    unavailable_nodes, {"imageGenNode": {"ok": True, "data": [
        item for item in catalog if item["id"] != config.SELFHOST_DEFAULT_IMAGE_SELECTION
    ]}}
)
print(json.dumps({
    "recommended": recommended_nodes[0]["data"]["model"],
    "recommendation_blockers": recommendation_blockers,
    "unavailable_blockers": [item["code"] for item in unavailable_blockers],
    "sketch": route(config.get_sketch_generation_config()),
    "render": route(config.get_render_generation_config()),
    "normalized": config.normalize_image_generation_selection("unknown"),
    "freezone": [
        config.SELFHOST_DEFAULT_IMAGE_SELECTION,
        schemas.FREEZONE_DEFAULT_IMAGE_MODEL,
        route_helpers.FREEZONE_DEFAULT_IMAGE_MODEL,
        presets.FREEZONE_PRESET_DEFAULT_IMAGE_MODEL,
        presets._image_gen_node("test", 0, 0, "test", "test")["data"]["model"],
    ],
    "schema_defaults": schema_defaults,
    "provider_defaults": [
        route_helpers.resolve_freezone_image_provider(None),
        route_helpers.resolve_freezone_image_provider(" "),
        route_helpers.resolve_freezone_image_provider("unsupported", strict=False),
    ],
    "explicit_providers": {
        value: route_helpers.resolve_freezone_image_provider(value)
        for value in ("provider_hub", "newapi", "openai", "openrouter", "huimeng")
    },
    "explicit_hub": route(config.get_render_generation_config("provider_hub_image")),
    "explicit_newapi": route(config.get_render_generation_config("newapi_gpt_image2")),
    "character": config.get_character_image_selection(),
    "strict_status": strict_status,
}))
"""


@pytest.mark.parametrize(
    "overrides,selection,sketch_provider,render_provider",
    [
        ({}, "provider_hub_image", "openai", "openai"),
        (
            {"DEFAULT_SKETCH_IMAGE_SELECTION": "provider_hub_image",
             "DEFAULT_RENDER_IMAGE_SELECTION": "provider_hub_image",
             "DEFAULT_CHARACTER_IMAGE_SELECTION": "provider_hub_image"},
            "provider_hub_image", "openai", "openai",
        ),
        (
            {"DEFAULT_SKETCH_IMAGE_SELECTION": "newapi_gpt_image2",
             "DEFAULT_RENDER_IMAGE_SELECTION": "newapi_gpt_image2"},
            "newapi_gpt_image2", "newapi", "newapi",
        ),
        (
            {"DEFAULT_SKETCH_IMAGE_SELECTION": "newapi_nanobanana2",
             "DEFAULT_RENDER_IMAGE_SELECTION": "newapi_nanobanana2"},
            "newapi_nanobanana2", "newapi", "newapi",
        ),
        (
            {"DEFAULT_SKETCH_IMAGE_SELECTION": "",
             "DEFAULT_RENDER_IMAGE_SELECTION": "invalid"},
            "provider_hub_image", "openrouter", "openai",
        ),
        (
            {"DEFAULT_SKETCH_IMAGE_SELECTION": "invalid",
             "DEFAULT_RENDER_IMAGE_SELECTION": "newapi_gpt_image2"},
            "newapi_gpt_image2", "newapi", "newapi",
        ),
        (
            {"DEFAULT_SKETCH_IMAGE_SELECTION": "newapi_gpt_image2"},
            "newapi_gpt_image2", "newapi", "openai",
        ),
        (
            {"DEFAULT_RENDER_IMAGE_SELECTION": "newapi_gpt_image2"},
            "provider_hub_image", "openai", "newapi",
        ),
        (
            {"NANOBANANA_PROVIDER": "openai"},
            "provider_hub_image", "openai", "openai",
        ),
    ],
    ids=["empty-env", "sample-hub", "newapi", "nb2",
         "invalid-defaults", "render-fallback", "sketch-only", "render-only", "legacy-provider"],
)
def test_selfhost_image_defaults_and_overrides(
    tmp_path: Path,
    overrides: dict[str, str],
    selection: str,
    sketch_provider: str,
    render_provider: str,
) -> None:
    # A fresh interpreter catches import-time defaults without leaking reloads to other tests.
    env = {
        key: value for key, value in os.environ.items()
        if key in ("PATH", "SYSTEMROOT")
    }
    env.update({
        "HOME": str(tmp_path),
        "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
        "PYTHON_DOTENV_DISABLED": "1",
        **overrides,
    })
    result = subprocess.run(
        [sys.executable, "-c", _PROBE], cwd=tmp_path, env=env,
        text=True, capture_output=True, check=True, timeout=60,
    )
    observed = json.loads(result.stdout.strip().splitlines()[-1])
    assert observed["recommended"] == "provider_hub_image"
    assert observed["recommendation_blockers"] == []
    assert observed["unavailable_blockers"] == ["recommended_model_unavailable"]
    assert observed["normalized"] == selection
    assert observed["freezone"] == ["provider_hub_image"] * 5
    assert len(observed["schema_defaults"]) == 7
    assert set(observed["schema_defaults"].values()) == {"provider_hub_image"}
    assert observed["provider_defaults"] == ["provider_hub"] * 3
    assert observed["sketch"]["provider"] == sketch_provider
    assert observed["render"]["provider"] == render_provider
    if not overrides or overrides.get("DEFAULT_SKETCH_IMAGE_SELECTION") == "provider_hub_image":
        assert observed["sketch"] == observed["explicit_hub"]
        assert observed["render"] == observed["explicit_hub"]
    if overrides.get("NANOBANANA_PROVIDER") == "openai":
        assert observed["sketch"]["model"] == "gpt-image-2"
        assert observed["render"]["model"] == "gpt-image-2"
    assert observed["explicit_hub"] == {
        "provider": "openai", "model": "DC-image",
        "base_url": "http://host.docker.internal:18001/v1",
    }
    assert observed["explicit_newapi"] == {
        "provider": "newapi", "model": "LingShan-G2",
        "base_url": "https://newapi.invalid/v1",
    }
    assert all(key == value for key, value in observed["explicit_providers"].items())
    assert observed["strict_status"] == 400
    # Historical character-model priority is deliberately outside this restoration.
    assert observed["character"] == overrides.get(
        "DEFAULT_CHARACTER_IMAGE_SELECTION", "newapi_nanobanana2"
    )
