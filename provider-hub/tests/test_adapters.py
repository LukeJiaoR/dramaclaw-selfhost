from __future__ import annotations

import base64

import httpx
import respx
from starlette.requests import Request

from provider_hub.adapters.comfyui import ComfyUIAdapter, inject_workflow
from provider_hub.adapters.mimo import MimoChatAudioAdapter
from provider_hub.adapters.openai import OpenAIAdapter
from provider_hub.models import ResolvedTarget, ServiceConfig


def target(protocol: str, service_type: str = "tts") -> ResolvedTarget:
    service = ServiceConfig(
        id="service-1",
        service_type=service_type,
        provider="xiaomi" if protocol == "mimo_chat_audio" else "openai",
        protocol=protocol,
        name="test",
        base_url="https://provider.test/v1",
        api_key="secret",
        models=("real-model",),
        default_model="real-model",
        settings={"voice_id": "configured-voice"},
    )
    return ResolvedTarget(service_type, service, "DC-alias", "real-model")


def voice_design_target() -> ResolvedTarget:
    resolved = target("mimo_chat_audio")
    return ResolvedTarget(
        resolved.capability,
        resolved.service,
        "DC-voice-design",
        "mimo-v2.5-tts-voicedesign",
    )


@respx.mock
async def test_mimo_adapter_transforms_request_and_decodes_audio():
    audio = b"fake-mp3"
    route = respx.post("https://provider.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"audio": {"data": base64.b64encode(audio).decode()}}}
                ]
            },
        )
    )

    response = await MimoChatAudioAdapter().invoke(
        target=target("mimo_chat_audio"),
        operation="audio_speech",
        payload={"model": "index-tts-2", "input": "你好"},
    )

    assert response.body == audio
    request = route.calls[0].request
    assert request.headers["api-key"] == "secret"
    assert request.headers.get("authorization") is None
    sent = __import__("json").loads(request.content)
    assert sent["model"] == "real-model"
    assert sent["messages"][0]["content"] == "你好"
    assert sent["audio"]["voice"] == "configured-voice"


@respx.mock
async def test_mimo_voice_design_forwards_description_as_user_message():
    audio = b"designed-voice"
    route = respx.post("https://provider.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"audio": {"data": base64.b64encode(audio).decode()}}}
                ]
            },
        )
    )

    response = await MimoChatAudioAdapter().invoke(
        target=voice_design_target(),
        operation="audio_speech",
        payload={
            "model": "DC-voice-design",
            "input": "这是一段声线试听。",
            "instructions": "中年女性，温和沉稳，标准普通话。",
        },
    )

    assert response.body == audio
    sent = __import__("json").loads(route.calls[0].request.content)
    assert sent["messages"] == [
        {"role": "user", "content": "中年女性，温和沉稳，标准普通话。"},
        {"role": "assistant", "content": "这是一段声线试听。"},
    ]
    assert sent["model"] == "mimo-v2.5-tts-voicedesign"
    assert sent["audio"] == {"format": "mp3"}


@respx.mock
async def test_openai_adapter_replaces_internal_model_name():
    route = respx.post("https://provider.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": []})
    )
    response = await OpenAIAdapter().invoke(
        target=target("openai", "text"),
        operation="chat_completions",
        payload={"model": "DC-scene-builder-LLM", "messages": []},
    )
    assert response.status_code == 200
    sent = __import__("json").loads(route.calls[0].request.content)
    assert sent["model"] == "real-model"


@respx.mock
async def test_openai_adapter_converts_multipart_image_edit_to_data_urls():
    route = respx.post("https://provider.test/v1/images/edits").mock(
        return_value=httpx.Response(200, json={"data": [{"b64_json": "aW1hZ2U="}]})
    )
    source = httpx.Request(
        "POST",
        "http://hub.test/v1/images/edits",
        data={"model": "DC-image", "prompt": "keep identity"},
        files={"image": ("portrait.png", b"portrait-bytes", "image/png")},
    )
    body = source.read()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/images/edits",
            "headers": [(key.lower(), value) for key, value in source.headers.raw],
        },
        receive,
    )
    response = await OpenAIAdapter().invoke(
        target=target("openai", "image"),
        operation="images_edits",
        payload={"model": "DC-image"},
        request=request,
    )

    assert response.status_code == 200
    sent = __import__("json").loads(route.calls[0].request.content)
    assert sent["model"] == "real-model"
    assert sent["prompt"] == "keep identity"
    assert sent["response_format"] == "b64_json"
    assert sent["image"] == [
        "data:image/png;base64," + base64.b64encode(b"portrait-bytes").decode()
    ]


def comfy_target() -> ResolvedTarget:
    service = ServiceConfig(
        id="comfy-1",
        service_type="video",
        provider="comfyui",
        protocol="comfyui_native",
        name="remote comfy",
        base_url="https://comfy.test",
        api_key="proxy-secret",
        models=("h3-local",),
        default_model="h3-local",
        settings={
            "workflows": [
                {
                    "id": "first-frame",
                    "modes": ["first_frame"],
                    "workflow": {
                        "1": {
                            "class_type": "LoadImage",
                            "inputs": {"image": "old.png"},
                        },
                        "2": {
                            "class_type": "CR Text",
                            "inputs": {"text": "old prompt"},
                        },
                        "3": {
                            "class_type": "FloatInput",
                            "_meta": {"title": "Seconds"},
                            "inputs": {"value": 3},
                        },
                        "4": {
                            "class_type": "VHS_VideoCombine",
                            "inputs": {"filename_prefix": "old"},
                        },
                    },
                }
            ]
        },
    )
    return ResolvedTarget("video", service, "h3-local", "h3-local")


def test_comfyui_workflow_semantic_injection():
    workflow = comfy_target().service.settings["workflows"][0]["workflow"]
    injected = inject_workflow(
        workflow,
        {"prompt": "new prompt", "duration": 7},
        {"images": ["provider-hub/first.png"], "audios": [], "videos": []},
    )
    assert injected["1"]["inputs"]["image"] == "provider-hub/first.png"
    assert injected["2"]["inputs"]["text"] == "new prompt"
    assert injected["3"]["inputs"]["value"] == 7
    assert injected["4"]["inputs"]["filename_prefix"].startswith("ProviderHub/")
    assert workflow["1"]["inputs"]["image"] == "old.png"


@respx.mock
async def test_comfyui_adapter_uploads_reference_and_submits_prompt():
    upload = respx.post("https://comfy.test/upload/image").mock(
        return_value=httpx.Response(
            200,
            json={"name": "0-first.png", "subfolder": "provider-hub", "type": "input"},
        )
    )
    prompt = respx.post("https://comfy.test/prompt").mock(
        return_value=httpx.Response(200, json={"prompt_id": "prompt-123"})
    )
    response = await ComfyUIAdapter().invoke(
        target=comfy_target(),
        operation="video_submit",
        payload={
            "model": "h3-local",
            "prompt": "animate",
            "duration": 5,
            "image": "data:image/png;base64," + base64.b64encode(b"png").decode(),
            "metadata": {},
        },
    )
    assert response.status_code == 201
    assert upload.called
    sent = __import__("json").loads(prompt.calls[0].request.content)
    assert sent["prompt"]["1"]["inputs"]["image"] == "provider-hub/0-first.png"
    assert sent["prompt"]["2"]["inputs"]["text"] == "animate"
    assert prompt.calls[0].request.headers["authorization"] == "Bearer proxy-secret"


@respx.mock
async def test_comfyui_adapter_normalizes_completed_history():
    respx.get("https://comfy.test/history/prompt-123").mock(
        return_value=httpx.Response(
            200,
            json={
                "prompt-123": {
                    "status": {"messages": []},
                    "outputs": {
                        "9": {
                            "gifs": [
                                {
                                    "filename": "movie.mp4",
                                    "subfolder": "ProviderHub",
                                    "type": "output",
                                }
                            ]
                        }
                    },
                }
            },
        )
    )
    response = await ComfyUIAdapter().query(comfy_target().service, "prompt-123")
    data = __import__("json").loads(response.body)
    assert data["status"] == "completed"
    assert data["output"]["filename"] == "movie.mp4"
