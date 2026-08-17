"""Shared OpenAI-compatible transport for DramaClaw text and vision calls."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any, Iterable

import httpx


def get_llm_gateway_credentials(
    *,
    api_key_override: str | None = None,
    base_url_override: str | None = None,
) -> tuple[str, str]:
    """Resolve credentials for the currently selected OpenAI-compatible gateway."""
    from novelvideo.config import get_newapi_runtime_credentials

    api_key, base_url = get_newapi_runtime_credentials(
        api_key_override=api_key_override,
        base_url_override=base_url_override,
        env_api_key="MODEL_API_KEY",
        env_base_url="MODEL_BASE_URL",
    )
    if not api_key:
        raise RuntimeError("Text/vision gateway API key is not configured")
    if not base_url:
        raise RuntimeError("Text/vision gateway base URL is not configured")
    return api_key, base_url.rstrip("/")


def _image_part(path: Path) -> dict[str, Any]:
    media_type = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{media_type};base64,{encoded}"},
    }


def _image_bytes_part(data: bytes, media_type: str) -> dict[str, Any]:
    encoded = base64.b64encode(data).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{media_type};base64,{encoded}"},
    }


async def call_llm_gateway(
    *,
    prompt: str,
    model: str,
    system_prompt: str = "",
    image_paths: Iterable[Path] = (),
    image_inputs: Iterable[tuple[bytes, str]] = (),
    api_key_override: str | None = None,
    base_url_override: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    response_format: dict[str, Any] | None = None,
    timeout_seconds: float = 120.0,
) -> str:
    """Call the active gateway through ``/chat/completions``."""
    api_key, base_url = get_llm_gateway_credentials(
        api_key_override=api_key_override,
        base_url_override=base_url_override,
    )
    paths = [Path(path) for path in image_paths]
    inputs = list(image_inputs)
    user_content: str | list[dict[str, Any]]
    if paths or inputs:
        user_content = [{"type": "text", "text": prompt}]
        user_content.extend(_image_part(path) for path in paths)
        user_content.extend(_image_bytes_part(data, media_type) for data, media_type in inputs)
    else:
        user_content = prompt

    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})
    payload: dict[str, Any] = {"model": model, "messages": messages}
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if response_format:
        payload["response_format"] = response_format

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    choices = data.get("choices") or []
    if not choices:
        return ""
    content = (choices[0].get("message") or {}).get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict)
        ).strip()
    return ""
