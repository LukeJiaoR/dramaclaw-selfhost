"""Small management client used to synchronize DramaClaw model routes."""

from __future__ import annotations

import json
from typing import Any

import httpx


VISION_MODEL_ALIASES = {
    "DC-video-prompt-optimizer-LLM",
    "DC-video-identity-detector-LLM",
    "DC-freezone-vision-LLM",
    "DC-style-analyzer-LLM",
    "DC-scene-spatial-contract-LLM",
    "DC-scene-overlap-analyzer-LLM",
    "DC-block-world-builder-LLM",
    "DC-sketch-visual-gate-LLM",
}


def _normalize_url(value: str) -> str:
    return str(value or "").strip().rstrip("/")


def provider_hub_management_url(gateway_base_url: str) -> str:
    base_url = _normalize_url(gateway_base_url)
    return base_url[:-3] if base_url.endswith("/v1") else base_url


def is_provider_hub_gateway(gateway_base_url: str | None) -> bool:
    from novelvideo.config import PROVIDER_HUB_BASE_URL

    return provider_hub_management_url(str(gateway_base_url or "")) == (
        provider_hub_management_url(PROVIDER_HUB_BASE_URL)
    )


def capability_for_model(model: str) -> str:
    return "vision" if model in VISION_MODEL_ALIASES else "text"


def _comparable_upstream_url(value: str) -> str:
    normalized = _normalize_url(value)
    return normalized[:-3] if normalized.endswith("/v1") else normalized


def _openai_compatible_upstream_url(provider: str, value: str) -> str:
    url = _normalize_url(value)
    lower = url.lower()
    if lower.endswith(("/v1", "/api/v1", "/api/v3", "/compatible-mode/v1")):
        return url
    suffixes = {
        "openai": "/v1",
        "openrouter": "/v1" if lower.endswith("/api") else "/api/v1",
        "ali": "/compatible-mode/v1",
        "volcengine": "/api/v3",
        "gemini": "/v1beta/openai",
    }
    return f"{url}{suffixes.get(provider, '/v1')}"


async def sync_provider_hub_channel(
    *,
    gateway_base_url: str,
    provider: str,
    name: str,
    upstream_key: str,
    upstream_base_url: str,
    model_mapping: dict[str, str],
    priority: int = 0,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create or reuse one Hub service and upsert all supplied model routes."""
    if not model_mapping:
        raise ValueError("modelMapping must not be empty")
    management_url = provider_hub_management_url(gateway_base_url)
    if not management_url:
        raise ValueError("Provider Hub base URL is required")
    provider = str(provider or "openai").strip().lower() or "openai"
    upstream_base_url = _normalize_url(upstream_base_url)
    if not upstream_base_url:
        raise ValueError(f"baseUrl is required for Provider Hub service {provider}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        state_response = await client.get(f"{management_url}/api/state")
        state_response.raise_for_status()
        state = state_response.json()
        services = state.get("services") or []
        resolved_upstream_base_url = _openai_compatible_upstream_url(
            provider, upstream_base_url
        )
        comparable = _comparable_upstream_url(resolved_upstream_base_url)
        service = next(
            (
                item
                for item in services
                if str(item.get("provider") or "").strip().lower() == provider
                and _comparable_upstream_url(str(item.get("base_url") or ""))
                == comparable
                and str(item.get("service_type") or "") in {"text", "vision"}
            ),
            None,
        )

        upstream_models = list(
            dict.fromkeys(str(value).strip() for value in model_mapping.values() if str(value).strip())
        )
        service_payload = {
            "service_type": "text",
            "provider": provider,
            "protocol": (
                str(service.get("protocol") or "openai_compatible")
                if service
                else "openai_compatible"
            ),
            "name": (
                str(service.get("name") or "")
                if service
                else name or f"DramaClaw {provider} text"
            ),
            "base_url": str(
                service.get("base_url")
                if service
                else resolved_upstream_base_url
            ),
            "api_key": upstream_key or None,
            "models": list(
                dict.fromkeys(
                    [
                        *((service.get("models") or []) if service else []),
                        *upstream_models,
                    ]
                )
            ),
            "default_model": (
                str(service.get("default_model") or "") if service else upstream_models[0]
            ),
            "endpoint": "/chat/completions",
            "priority": int(priority),
            "is_default": bool(service.get("is_default")) if service else False,
            "is_active": True,
            "settings": settings or (service.get("settings") if service else {}) or {},
        }
        if service:
            service_response = await client.put(
                f"{management_url}/api/services/{service['id']}", json=service_payload
            )
        else:
            service_response = await client.post(
                f"{management_url}/api/services", json=service_payload
            )
        service_response.raise_for_status()
        saved_service = service_response.json()
        service_id = str(saved_service["id"])

        routes: list[str] = []
        for incoming_model, upstream_model in model_mapping.items():
            incoming_model = str(incoming_model or "").strip()
            upstream_model = str(upstream_model or "").strip()
            if not incoming_model or not upstream_model:
                continue
            route_response = await client.post(
                f"{management_url}/api/routes",
                json={
                    "incoming_model": incoming_model,
                    "capability": capability_for_model(incoming_model),
                    "service_id": service_id,
                    "upstream_model": upstream_model,
                },
            )
            route_response.raise_for_status()
            routes.append(incoming_model)

    return {
        "ok": True,
        "action": "provider_hub_synced",
        "serviceId": service_id,
        "routes": routes,
        "service": {
            "name": saved_service.get("name"),
            "provider": saved_service.get("provider"),
            "baseUrl": saved_service.get("base_url"),
        },
    }


def mapping_from_channel_payload(payload: dict[str, Any]) -> dict[str, str]:
    channel = payload.get("channel") or {}
    value = channel.get("model_mapping")
    if isinstance(value, str):
        value = json.loads(value or "{}")
    if not isinstance(value, dict):
        return {}
    return {
        str(key).strip(): str(item).strip()
        for key, item in value.items()
        if str(key).strip() and str(item).strip()
    }


async def sync_provider_hub_channel_payload(
    *, gateway_base_url: str, provider: str, payload: dict[str, Any]
) -> dict[str, Any]:
    channel = payload.get("channel") or {}
    settings = channel.get("settings") or "{}"
    if isinstance(settings, str):
        settings = json.loads(settings or "{}")
    return await sync_provider_hub_channel(
        gateway_base_url=gateway_base_url,
        provider=provider,
        name=str(channel.get("name") or ""),
        upstream_key=str(channel.get("key") or ""),
        upstream_base_url=str(channel.get("base_url") or ""),
        model_mapping=mapping_from_channel_payload(payload),
        priority=int(channel.get("priority") or 0),
        settings=settings if isinstance(settings, dict) else {},
    )


async def update_provider_hub_service_credentials(
    *,
    gateway_base_url: str,
    provider: str,
    upstream_key: str,
    upstream_base_url: str = "",
) -> dict[str, Any]:
    management_url = provider_hub_management_url(gateway_base_url)
    provider = str(provider or "").strip().lower()
    requested_url = _normalize_url(upstream_base_url)
    async with httpx.AsyncClient(timeout=30.0) as client:
        state_response = await client.get(f"{management_url}/api/state")
        state_response.raise_for_status()
        services = state_response.json().get("services") or []
        candidates = [
            item
            for item in services
            if str(item.get("provider") or "").strip().lower() == provider
            and str(item.get("service_type") or "") in {"text", "vision"}
        ]
        if requested_url:
            comparable = _comparable_upstream_url(
                _openai_compatible_upstream_url(provider, requested_url)
            )
            candidates = [
                item
                for item in candidates
                if _comparable_upstream_url(str(item.get("base_url") or ""))
                == comparable
            ]
        if not candidates:
            raise LookupError(f"Provider Hub service not found for provider {provider}")
        service = candidates[0]
        resolved_url = (
            _openai_compatible_upstream_url(provider, requested_url)
            if requested_url
            else str(service.get("base_url") or "")
        )
        response = await client.put(
            f"{management_url}/api/services/{service['id']}",
            json={
                "service_type": str(service.get("service_type") or "text"),
                "provider": provider,
                "protocol": str(service.get("protocol") or "openai_compatible"),
                "name": str(service.get("name") or provider),
                "base_url": resolved_url,
                "api_key": upstream_key or None,
                "models": service.get("models") or [],
                "default_model": str(service.get("default_model") or ""),
                "endpoint": str(service.get("endpoint") or "/chat/completions"),
                "query_endpoint": str(service.get("query_endpoint") or ""),
                "priority": int(service.get("priority") or 0),
                "is_default": bool(service.get("is_default")),
                "is_active": bool(service.get("is_active", True)),
                "settings": service.get("settings") or {},
            },
        )
        response.raise_for_status()
    return {
        "ok": True,
        "action": "provider_hub_credentials_updated",
        "serviceId": str(service["id"]),
    }
