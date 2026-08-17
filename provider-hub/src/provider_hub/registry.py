from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any, Protocol

from fastapi import Request, Response

from provider_hub.models import ResolvedTarget


class ProviderAdapter(Protocol):
    protocols: tuple[str, ...]

    async def invoke(
        self,
        *,
        target: ResolvedTarget,
        operation: str,
        payload: dict[str, Any],
        request: Request | None = None,
    ) -> Response: ...


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, ProviderAdapter] = {}

    def register(self, adapter: ProviderAdapter) -> None:
        for protocol in adapter.protocols:
            self._adapters[protocol.strip().lower()] = adapter

    def get(self, protocol: str) -> ProviderAdapter:
        adapter = self._adapters.get(protocol.strip().lower())
        if adapter is None:
            raise LookupError(f"no adapter installed for protocol: {protocol}")
        return adapter

    def protocols(self) -> list[str]:
        return sorted(self._adapters)

    def load_entry_points(self) -> None:
        for entry_point in entry_points(group="dramaclaw_provider_hub.adapters"):
            entry_point.load()(self)


registry = AdapterRegistry()


def load_builtin_adapters() -> AdapterRegistry:
    if registry.protocols():
        return registry
    from provider_hub.adapters import comfyui, mimo, openai, video

    openai.register(registry)
    mimo.register(registry)
    video.register(registry)
    comfyui.register(registry)
    try:
        registry.load_entry_points()
    except Exception:
        pass
    return registry
