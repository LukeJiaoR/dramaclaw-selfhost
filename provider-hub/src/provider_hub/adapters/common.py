from __future__ import annotations

from typing import Any, AsyncIterator

import httpx
from fastapi import Response
from fastapi.responses import StreamingResponse

from provider_hub.models import ServiceConfig


HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "content-encoding",
}


def join_url(base_url: str, endpoint: str) -> str:
    base = base_url.rstrip("/")
    endpoint = endpoint.strip()
    if not endpoint:
        return base
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        return endpoint
    return f"{base}/{endpoint.lstrip('/')}"


def auth_headers(service: ServiceConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if service.api_key:
        headers["Authorization"] = f"Bearer {service.api_key}"
    custom = service.settings.get("headers")
    if isinstance(custom, dict):
        headers.update({str(k): str(v) for k, v in custom.items()})
    return headers


def response_headers(headers: httpx.Headers) -> dict[str, str]:
    return {
        key: value for key, value in headers.items() if key.lower() not in HOP_HEADERS
    }


async def buffered_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
    timeout: float = 600.0,
) -> Response:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        result = await client.request(method, url, headers=headers, json=payload)
    return Response(
        content=result.content,
        status_code=result.status_code,
        headers=response_headers(result.headers),
        media_type=result.headers.get("content-type"),
    )


async def streaming_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float = 600.0,
) -> StreamingResponse:
    client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)
    request = client.build_request(method, url, headers=headers, json=payload)
    upstream = await client.send(request, stream=True)

    async def body() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        body(),
        status_code=upstream.status_code,
        headers=response_headers(upstream.headers),
        media_type=upstream.headers.get("content-type"),
    )
