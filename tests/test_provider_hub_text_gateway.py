from __future__ import annotations

import json

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from novelvideo.api.routes import model_gateway
from novelvideo.llm_gateway import call_llm_gateway
from novelvideo.provider_hub_admin import (
    capability_for_model,
    is_provider_hub_gateway,
    sync_provider_hub_channel,
)


@pytest.mark.asyncio
@respx.mock
async def test_llm_gateway_sends_vision_request_to_effective_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "novelvideo.config.get_newapi_runtime_credentials",
        lambda **_kwargs: ("hub-key", "http://hub.test/v1"),
    )
    route = respx.post("http://hub.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok":true}'}}]},
        )
    )

    result = await call_llm_gateway(
        prompt="inspect",
        model="DC-freezone-vision-LLM",
        image_inputs=[(b"image-bytes", "image/png")],
        response_format={"type": "json_object"},
    )

    assert result == '{"ok":true}'
    request = route.calls[0].request
    assert request.headers["authorization"] == "Bearer hub-key"
    payload = json.loads(request.content)
    assert payload["model"] == "DC-freezone-vision-LLM"
    image_url = payload["messages"][0]["content"][1]["image_url"]["url"]
    assert image_url.startswith("data:image/png;base64,")


@pytest.mark.asyncio
@respx.mock
async def test_sync_provider_hub_channel_reuses_service_and_writes_capabilities() -> None:
    respx.get("http://hub.test/api/state").mock(
        return_value=httpx.Response(
            200,
            json={
                "services": [
                    {
                        "id": "service-1",
                        "service_type": "text",
                        "provider": "openai",
                        "name": "Existing text",
                        "base_url": "https://upstream.test/v1",
                        "models": ["existing-model"],
                        "default_model": "existing-model",
                        "is_default": True,
                        "settings": {},
                    }
                ]
            },
        )
    )
    update = respx.put("http://hub.test/api/services/service-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "service-1",
                "provider": "openai",
                "name": "Existing text",
                "base_url": "https://upstream.test/v1",
            },
        )
    )
    routes = respx.post("http://hub.test/api/routes").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    result = await sync_provider_hub_channel(
        gateway_base_url="http://hub.test/v1",
        provider="openai",
        name="DramaClaw openai",
        upstream_key="upstream-key",
        upstream_base_url="https://upstream.test",
        model_mapping={
            "DC-freezone-text-writer-LLM": "text-model",
            "DC-freezone-vision-LLM": "vision-model",
        },
    )

    assert result["routes"] == [
        "DC-freezone-text-writer-LLM",
        "DC-freezone-vision-LLM",
    ]
    service_payload = json.loads(update.calls[0].request.content)
    assert service_payload["models"] == [
        "existing-model",
        "text-model",
        "vision-model",
    ]
    route_payloads = [json.loads(call.request.content) for call in routes.calls]
    assert [item["capability"] for item in route_payloads] == ["text", "vision"]
    assert all(item["service_id"] == "service-1" for item in route_payloads)


def test_provider_hub_detection_and_model_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "novelvideo.config.PROVIDER_HUB_BASE_URL", "http://hub.test/v1"
    )
    assert is_provider_hub_gateway("http://hub.test/v1")
    assert is_provider_hub_gateway("http://hub.test")
    assert not is_provider_hub_gateway("http://newapi.test/v1")
    assert capability_for_model("DC-scene-spatial-contract-LLM") == "vision"
    assert capability_for_model("DC-freezone-text-writer-LLM") == "text"


def test_feature_model_batch_uses_provider_hub_instead_of_newapi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synced: list[dict[str, object]] = []

    monkeypatch.setattr(model_gateway, "require_ce_gateway_management", lambda: None)
    monkeypatch.setattr(model_gateway, "is_provider_hub_gateway", lambda _url: True)
    monkeypatch.setattr(
        model_gateway,
        "get_provisioner_config",
        lambda *_args, **_kwargs: type(
            "Cfg", (), {"admin_base_url": "http://legacy-newapi:3000"}
        )(),
    )
    monkeypatch.setattr(
        model_gateway,
        "ensure_admin_access_token",
        lambda _cfg: pytest.fail("NewAPI admin must not be used in Provider Hub mode"),
    )

    async def fake_sync(**kwargs):
        synced.append(kwargs)
        return {
            "ok": True,
            "action": "provider_hub_synced",
            "serviceId": "service-1",
            "routes": ["DC-freezone-text-writer-LLM"],
        }

    monkeypatch.setattr(model_gateway, "sync_provider_hub_channel_payload", fake_sync)

    app = FastAPI()
    app.include_router(model_gateway.router)
    response = TestClient(app).post(
        "/model-gateway/custom/newapi/channels/batch",
        json={
            "newApiBaseUrl": "http://hub.test/v1",
            "channels": [
                {
                    "provider": "openai",
                    "upstreamKey": "upstream-secret",
                    "baseUrl": "https://upstream.test/v1",
                    "modelMapping": {
                        "DC-freezone-text-writer-LLM": "gpt-text"
                    },
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert synced[0]["gateway_base_url"] == "http://hub.test/v1"
    assert synced[0]["provider"] == "openai"
    assert "upstream-secret" not in response.text
