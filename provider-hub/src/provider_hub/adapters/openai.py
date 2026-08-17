from __future__ import annotations

import base64
from typing import Any

from fastapi import Request, Response

from provider_hub.adapters.common import (
    auth_headers,
    buffered_request,
    join_url,
    streaming_request,
)
from provider_hub.models import ResolvedTarget


DEFAULT_ENDPOINTS = {
    "chat_completions": "/chat/completions",
    "embeddings": "/embeddings",
    "images_generations": "/images/generations",
    "images_edits": "/images/edits",
    "audio_speech": "/audio/speech",
}


class OpenAIAdapter:
    protocols = ("openai", "openai_compatible", "openai_audio_speech")

    async def invoke(
        self,
        *,
        target: ResolvedTarget,
        operation: str,
        payload: dict[str, Any],
        request: Request | None = None,
    ) -> Response:
        service = target.service
        body = dict(payload)
        if target.upstream_model:
            body["model"] = target.upstream_model
        configured_endpoint = service.endpoint if operation != "images_edits" else ""
        endpoint = configured_endpoint or DEFAULT_ENDPOINTS.get(
            operation, f"/{operation}"
        )
        url = join_url(service.base_url, endpoint)
        headers = auth_headers(service)
        if (
            operation == "images_edits"
            and request is not None
            and "multipart/form-data" in request.headers.get("content-type", "")
        ):
            form = await request.form()
            body = {}
            images: list[str] = []
            for key, value in form.multi_items():
                if hasattr(value, "filename") and hasattr(value, "read"):
                    content = await value.read()
                    mime_type = str(value.content_type or "image/png")
                    images.append(
                        f"data:{mime_type};base64,{base64.b64encode(content).decode()}"
                    )
                else:
                    body[key] = str(value)
            body["model"] = target.upstream_model or service.default_model
            body["image"] = images
            body.setdefault("response_format", "b64_json")
            return await buffered_request("POST", url, headers=headers, payload=body)
        if body.get("stream"):
            return await streaming_request("POST", url, headers=headers, payload=body)
        return await buffered_request("POST", url, headers=headers, payload=body)


def register(registry) -> None:
    registry.register(OpenAIAdapter())
