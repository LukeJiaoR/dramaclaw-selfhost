from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import Request, Response

from provider_hub.adapters.common import auth_headers, join_url
from provider_hub.models import ResolvedTarget, ServiceConfig


def _first(data: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        value: Any = data
        for part in path.split("."):
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(part)
        if value not in (None, ""):
            return value
    return None


def extract_task_id(data: dict[str, Any]) -> str:
    return str(_first(data, "id", "task_id", "taskId", "data.id", "data.task_id") or "")


def normalize_task(data: dict[str, Any]) -> dict[str, Any]:
    raw_status = str(
        _first(data, "status", "state", "data.status", "data.state") or "queued"
    ).lower()
    status_map = {
        "pending": "queued",
        "created": "queued",
        "processing": "running",
        "in_progress": "running",
        "succeeded": "completed",
        "success": "completed",
        "done": "completed",
        "failed": "failed",
        "error": "failed",
        "cancelled": "failed",
    }
    result = dict(data)
    result["status"] = status_map.get(raw_status, raw_status)
    url = _first(
        data,
        "video_url",
        "url",
        "output_url",
        "data.video_url",
        "data.url",
        "content.video_url",
        "result.video_url",
        "output.video_url",
    )
    if url:
        result["video_url"] = str(url)
    error = _first(data, "error", "message", "fail_reason", "data.error")
    if result["status"] == "failed" and error:
        result["error"] = error
    return result


class GenericVideoAdapter:
    protocols = (
        "openai_video",
        "volcengine_omni",
        "volces",
        "xai",
        "veo3",
        "gemini_video",
    )

    def submit_endpoint(self, service: ServiceConfig) -> str:
        if service.endpoint:
            return service.endpoint
        if service.protocol == "xai":
            return "/v1/videos/generations"
        return "/video/generations"

    def query_endpoint(self, service: ServiceConfig, task_id: str) -> str:
        endpoint = service.query_endpoint
        if not endpoint:
            if service.protocol == "xai":
                endpoint = "/v1/videos/{taskId}"
            else:
                endpoint = "/video/generations/{taskId}"
        return endpoint.replace("{taskId}", task_id).replace("{task_id}", task_id)

    def headers(self, service: ServiceConfig) -> dict[str, str]:
        headers = auth_headers(service)
        if service.protocol in {"veo3", "gemini_video"} and service.api_key:
            headers.pop("Authorization", None)
            headers["x-goog-api-key"] = service.api_key
        return headers

    async def invoke(
        self,
        *,
        target: ResolvedTarget,
        operation: str,
        payload: dict[str, Any],
        request: Request | None = None,
    ) -> Response:
        service = target.service
        if operation != "video_submit":
            raise ValueError("video polling is handled by the gateway task router")
        body = dict(payload)
        body["model"] = target.upstream_model
        endpoint = self.submit_endpoint(service).replace("{model}", target.upstream_model)
        url = join_url(service.base_url, endpoint)
        async with httpx.AsyncClient(timeout=600.0, follow_redirects=True) as client:
            result = await client.post(url, headers=self.headers(service), json=body)
        return Response(
            content=result.content,
            status_code=result.status_code,
            media_type=result.headers.get("content-type"),
        )

    async def query(self, service: ServiceConfig, upstream_task_id: str) -> Response:
        url = join_url(service.base_url, self.query_endpoint(service, upstream_task_id))
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            result = await client.get(url, headers=self.headers(service))
        return Response(
            content=result.content,
            status_code=result.status_code,
            media_type=result.headers.get("content-type"),
        )


def register(registry) -> None:
    registry.register(GenericVideoAdapter())
