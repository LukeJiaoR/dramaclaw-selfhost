from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


CAPABILITIES = {
    "text",
    "vision",
    "embedding",
    "image",
    "storyboard_image",
    "video",
    "tts",
}


@dataclass(frozen=True)
class ServiceConfig:
    id: str
    service_type: str
    provider: str
    protocol: str
    name: str
    base_url: str
    api_key: str
    models: tuple[str, ...]
    default_model: str
    endpoint: str = ""
    query_endpoint: str = ""
    priority: int = 0
    is_default: bool = False
    is_active: bool = True
    settings: dict[str, Any] = field(default_factory=dict)
    source: str = "manual"
    source_id: str = ""


@dataclass(frozen=True)
class ResolvedTarget:
    capability: str
    service: ServiceConfig
    incoming_model: str
    upstream_model: str


@dataclass(frozen=True)
class ProxyResult:
    status_code: int
    headers: dict[str, str]
    content: bytes


def infer_protocol(
    service_type: str,
    provider: str,
    explicit: str = "",
    base_url: str = "",
) -> str:
    explicit = explicit.strip().lower()
    provider = provider.strip().lower()
    service_type = service_type.strip().lower()
    if service_type == "tts":
        if provider in {"xiaomi", "mimo"} or "xiaomimimo.com" in base_url.lower():
            return "mimo_chat_audio"
        if provider == "minimax":
            return "minimax_t2a"
        return explicit or "openai_audio_speech"
    if explicit:
        return explicit
    if service_type == "video":
        return provider or "openai_video"
    return "openai"
