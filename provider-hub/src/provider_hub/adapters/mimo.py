from __future__ import annotations

import base64
from typing import Any

import httpx
from fastapi import Request, Response

from provider_hub.adapters.common import join_url
from provider_hub.models import ResolvedTarget


class MimoChatAudioAdapter:
    protocols = ("mimo_chat_audio",)

    async def invoke(
        self,
        *,
        target: ResolvedTarget,
        operation: str,
        payload: dict[str, Any],
        request: Request | None = None,
    ) -> Response:
        if operation != "audio_speech":
            raise ValueError("MiMo adapter only supports audio_speech")
        service = target.service
        voice = str(
            payload.get("voice")
            or service.settings.get("voice_id")
            or "mimo_default"
        ).strip()
        response_format = str(payload.get("response_format") or "mp3").strip().lower()
        instructions = str(
            payload.get("instructions")
            or payload.get("voice_description")
            or ""
        ).strip()
        messages = []
        if instructions:
            messages.append({"role": "user", "content": instructions})
        messages.append(
            {"role": "assistant", "content": str(payload.get("input") or "")}
        )
        upstream_model = target.upstream_model or "mimo-v2.5-tts"
        audio_options = {"format": response_format}
        if "voicedesign" not in upstream_model.lower():
            audio_options["voice"] = voice
        body = {
            "model": upstream_model,
            "messages": messages,
            "audio": audio_options,
        }
        endpoint = service.endpoint or "/chat/completions"
        url = join_url(service.base_url, endpoint)
        headers = {"Content-Type": "application/json"}
        if service.api_key:
            headers["api-key"] = service.api_key
        async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as client:
            result = await client.post(url, headers=headers, json=body)
        if result.status_code < 200 or result.status_code >= 300:
            return Response(
                content=result.content,
                status_code=result.status_code,
                media_type=result.headers.get("content-type"),
            )
        try:
            encoded = result.json()["choices"][0]["message"]["audio"]["data"]
            audio = base64.b64decode(encoded, validate=True)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            return Response(
                content=f"MiMo response missing valid audio data: {exc}",
                status_code=502,
                media_type="text/plain",
            )
        mime = {
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "opus": "audio/opus",
            "pcm": "audio/L16",
        }.get(response_format, "audio/mpeg")
        return Response(content=audio, media_type=mime)


def register(registry) -> None:
    registry.register(MimoChatAudioAdapter())
