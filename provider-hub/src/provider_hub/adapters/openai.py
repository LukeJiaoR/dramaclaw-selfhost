from __future__ import annotations

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
        endpoint = configured_endpoint or DEFAULT_ENDPOINTS.get(operation, f"/{operation}")
        url = join_url(service.base_url, endpoint)
        headers = auth_headers(service)
        if body.get("stream"):
            return await streaming_request("POST", url, headers=headers, payload=body)
        return await buffered_request("POST", url, headers=headers, payload=body)


def register(registry) -> None:
    registry.register(OpenAIAdapter())
