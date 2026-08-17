from __future__ import annotations

import base64
import copy
import json
import mimetypes
import re
import urllib.parse
from pathlib import Path
from typing import Any

import httpx
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from provider_hub.adapters.common import auth_headers, join_url
from provider_hub.models import ResolvedTarget, ServiceConfig


def _title(node: dict[str, Any]) -> str:
    meta = node.get("_meta")
    return str(meta.get("title") if isinstance(meta, dict) else "").lower()


def _entries(workflow: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    def key(item: tuple[str, Any]) -> tuple[int, str]:
        node_id = str(item[0])
        return (int(node_id) if node_id.isdigit() else 2**31, node_id)

    return [
        (str(node_id), node)
        for node_id, node in sorted(workflow.items(), key=key)
        if isinstance(node, dict) and isinstance(node.get("inputs"), dict)
    ]


def _set_input(node: dict[str, Any], value: Any, *names: str) -> bool:
    inputs = node["inputs"]
    for name in names:
        if name in inputs:
            inputs[name] = value
            return True
    if names:
        inputs[names[0]] = value
        return True
    return False


def _binding_items(value: Any) -> list[dict[str, str]]:
    if isinstance(value, dict):
        return [{"node": str(value.get("node") or ""), "input": str(value.get("input") or "")}]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def inject_workflow(
    template: dict[str, Any],
    payload: dict[str, Any],
    uploaded: dict[str, list[str]],
    bindings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workflow = copy.deepcopy(template)
    entries = _entries(workflow)
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    values: dict[str, Any] = {
        "prompt": str(payload.get("prompt") or ""),
        "duration": payload.get("duration") or payload.get("seconds") or 5,
        "width": payload.get("width"),
        "height": payload.get("height"),
        "seed": payload.get("seed", metadata.get("seed")),
        "output_prefix": f"ProviderHub/{payload.get('_hub_task_hint') or 'video'}",
    }

    explicitly_bound: set[str] = set()
    for name, specs in (bindings or {}).items():
        source = uploaded.get(name) if name in {"images", "audios", "videos"} else values.get(name)
        if source in (None, "", []):
            continue
        items = source if isinstance(source, list) else [source]
        for index, spec in enumerate(_binding_items(specs)):
            node = workflow.get(str(spec.get("node") or ""))
            input_name = str(spec.get("input") or "")
            if isinstance(node, dict) and isinstance(node.get("inputs"), dict) and input_name:
                node["inputs"][input_name] = items[min(index, len(items) - 1)]
                explicitly_bound.add(str(name))

    def nodes(class_name: str) -> list[dict[str, Any]]:
        return [node for _, node in entries if str(node.get("class_type") or "") == class_name]

    if "images" not in explicitly_bound:
        image_nodes = nodes("LoadImage")
        for index, name in enumerate(uploaded.get("images", [])):
            if index < len(image_nodes):
                _set_input(image_nodes[index], name, "image")
    if "audios" not in explicitly_bound:
        audio_nodes = nodes("LoadAudio")
        for index, name in enumerate(uploaded.get("audios", [])):
            if index < len(audio_nodes):
                _set_input(audio_nodes[index], name, "audio")
    if "videos" not in explicitly_bound:
        video_nodes = [
            node
            for _, node in entries
            if str(node.get("class_type") or "") in {"LoadVideo", "VHS_LoadVideo"}
        ]
        for index, name in enumerate(uploaded.get("videos", [])):
            if index < len(video_nodes):
                _set_input(video_nodes[index], name, "video", "video_path")

    if "prompt" not in explicitly_bound:
        prompt_nodes = [
            node
            for _, node in entries
            if "prompt" in _title(node)
            or "提示" in _title(node)
            or str(node.get("class_type") or "") == "CR Text"
        ]
        if not prompt_nodes:
            prompt_nodes = [
                node
                for _, node in entries
                if str(node.get("class_type") or "") in {"CLIPTextEncode", "Text Multiline"}
                and "negative" not in _title(node)
                and "负面" not in _title(node)
            ]
        if prompt_nodes:
            _set_input(prompt_nodes[0], values["prompt"], "text", "prompt")

    semantic = {
        "duration": (("second", "duration", "秒", "时长"), ("value", "seconds", "duration", "Number")),
        "width": (("width", "宽"), ("width", "value", "Number")),
        "height": (("height", "高"), ("height", "value", "Number")),
        "seed": (("seed", "种子"), ("noise_seed", "seed", "value")),
    }
    for name, (title_terms, input_names) in semantic.items():
        if name in explicitly_bound or values.get(name) in (None, ""):
            continue
        candidates = [node for _, node in entries if any(term in _title(node) for term in title_terms)]
        if name == "seed" and not candidates:
            candidates = nodes("RandomNoise")
        if candidates:
            _set_input(candidates[0], values[name], *input_names)

    if "output_prefix" not in explicitly_bound:
        output_nodes = [
            node
            for _, node in entries
            if str(node.get("class_type") or "") in {"VHS_VideoCombine", "SaveImage", "SaveVideo"}
        ]
        if output_nodes:
            _set_input(output_nodes[0], values["output_prefix"], "filename_prefix")
    return workflow


def extract_output(history_item: dict[str, Any]) -> dict[str, str] | None:
    outputs = history_item.get("outputs")
    if not isinstance(outputs, dict):
        return None
    for node_output in outputs.values():
        if not isinstance(node_output, dict):
            continue
        for key in ("videos", "gifs", "images", "audio"):
            items = node_output.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict) and item.get("filename"):
                    return {
                        "filename": str(item["filename"]),
                        "subfolder": str(item.get("subfolder") or ""),
                        "type": str(item.get("type") or "output"),
                    }
    return None


class ComfyUIAdapter:
    protocols = ("comfyui", "comfyui_native")

    @staticmethod
    def _headers(service: ServiceConfig) -> dict[str, str]:
        return auth_headers(service)

    @staticmethod
    def _mode(payload: dict[str, Any]) -> str:
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        explicit = str(metadata.get("mode") or metadata.get("gen_mode") or "").strip()
        if explicit:
            return explicit
        if payload.get("image") and metadata.get("last_frame_image"):
            return "first_last_frame"
        if any(metadata.get(key) for key in ("reference_images", "reference_videos", "reference_audios")):
            return "all_reference"
        if payload.get("image"):
            return "first_frame"
        return "text_to_video"

    @staticmethod
    def _mode_candidates(payload: dict[str, Any]) -> list[str]:
        mode = ComfyUIAdapter._mode(payload)
        aliases = {
            "first_frame": ["first_frame", "image_to_video"],
            "all_reference": ["all_reference", "image_reference"],
        }
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        if metadata.get("reference_videos"):
            return ["video_edit", "all_reference"]
        return aliases.get(mode, [mode])

    @staticmethod
    def _workflow(service: ServiceConfig, target: ResolvedTarget, payload: dict[str, Any]) -> dict[str, Any]:
        settings = service.settings
        configured = settings.get("workflows")
        routes: list[dict[str, Any]] = []
        if isinstance(configured, list):
            routes = [item for item in configured if isinstance(item, dict)]
        elif isinstance(configured, dict):
            routes = [
                {"id": str(route_id), "workflow": workflow}
                for route_id, workflow in configured.items()
                if isinstance(workflow, dict)
            ]
        legacy = settings.get("workflow_by_model")
        if not routes and isinstance(legacy, dict):
            workflow = legacy.get(target.upstream_model) or legacy.get(target.incoming_model)
            if isinstance(workflow, dict):
                routes = [{"id": target.upstream_model, "workflow": workflow}]
        direct = settings.get("workflow")
        if not routes and isinstance(direct, dict):
            routes = [{"id": "default", "workflow": direct}]
        modes_for_request = ComfyUIAdapter._mode_candidates(payload)
        mode = modes_for_request[0]
        model = target.upstream_model or target.incoming_model
        fallback: dict[str, Any] | None = None
        for route in routes:
            match = route.get("match") if isinstance(route.get("match"), dict) else {}
            modes = route.get("modes") or match.get("modes", [])
            models = route.get("models") or match.get("models", [])
            if models and model not in [str(item) for item in models]:
                continue
            workflow = route.get("workflow")
            if not isinstance(workflow, dict) or not workflow:
                continue
            if modes:
                if set(modes_for_request).intersection(str(item) for item in modes):
                    return route
                continue
            if models:
                return route
            if fallback is None:
                fallback = route
        if fallback:
            return fallback
        raise ValueError(f"no ComfyUI workflow configured for model={model}, mode={mode}")

    @staticmethod
    def _references(payload: dict[str, Any]) -> list[tuple[str, str]]:
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        result: list[tuple[str, str]] = []
        if payload.get("image"):
            result.append(("image", str(payload["image"])))
        if metadata.get("last_frame_image"):
            result.append(("image", str(metadata["last_frame_image"])))
        for kind, key in (("image", "reference_images"), ("video", "reference_videos"), ("audio", "reference_audios")):
            values = metadata.get(key)
            if isinstance(values, list):
                result.extend((kind, str(value)) for value in values if value)
        return result

    async def _read_asset(self, client: httpx.AsyncClient, value: str) -> tuple[bytes, str, str]:
        if value.startswith("data:"):
            header, encoded = value.split(",", 1)
            mime = header[5:].split(";", 1)[0] or "application/octet-stream"
            content = base64.b64decode(encoded) if ";base64" in header else urllib.parse.unquote_to_bytes(encoded)
            extension = mimetypes.guess_extension(mime) or ".bin"
            return content, f"reference{extension}", mime
        if not value.startswith(("http://", "https://")):
            raise ValueError("ComfyUI references must be HTTP(S) or data URLs")
        response = await client.get(value)
        response.raise_for_status()
        mime = response.headers.get("content-type", "application/octet-stream").split(";", 1)[0]
        filename = Path(urllib.parse.urlsplit(value).path).name or f"reference{mimetypes.guess_extension(mime) or '.bin'}"
        return response.content, filename, mime

    async def _upload(self, client: httpx.AsyncClient, service: ServiceConfig, kind: str, value: str, index: int) -> str:
        content, filename, mime = await self._read_asset(client, value)
        endpoints = service.settings.get("upload_endpoints")
        endpoint = endpoints.get(kind) if isinstance(endpoints, dict) else None
        endpoint = str(endpoint or "/upload/image")
        subfolder = str(service.settings.get("upload_subfolder") or "provider-hub")
        headers = self._headers(service)
        headers.pop("Content-Type", None)
        response = await client.post(
            join_url(service.base_url, endpoint),
            headers=headers,
            data={"type": "input", "subfolder": subfolder, "overwrite": "true"},
            files={"image": (f"{index}-{filename}", content, mime)},
        )
        response.raise_for_status()
        data = response.json()
        name = str(data.get("name") or f"{index}-{filename}")
        returned_subfolder = str(data.get("subfolder") or subfolder).strip("/")
        return f"{returned_subfolder}/{name}" if returned_subfolder else name

    async def invoke(
        self,
        *,
        target: ResolvedTarget,
        operation: str,
        payload: dict[str, Any],
        request: Request | None = None,
    ) -> Response:
        if operation != "video_submit":
            raise ValueError("ComfyUI adapter only supports video submission")
        route = self._workflow(target.service, target, payload)
        uploaded: dict[str, list[str]] = {"images": [], "audios": [], "videos": []}
        timeout = float(target.service.settings.get("timeout_seconds") or 600)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            for index, (kind, value) in enumerate(self._references(payload)):
                uploaded[f"{kind}s"].append(await self._upload(client, target.service, kind, value, index))
            workflow = inject_workflow(
                route["workflow"], payload, uploaded,
                route.get("bindings") if isinstance(route.get("bindings"), dict) else {},
            )
            response = await client.post(
                join_url(target.service.base_url, "/prompt"),
                headers=self._headers(target.service),
                json={"prompt": workflow, "client_id": "dramaclaw-provider-hub"},
            )
        if response.status_code < 200 or response.status_code >= 300:
            return Response(content=response.content, status_code=response.status_code, media_type=response.headers.get("content-type"))
        data = response.json()
        prompt_id = str(data.get("prompt_id") or "")
        if not prompt_id:
            return JSONResponse(status_code=502, content={"error": "ComfyUI did not return prompt_id"})
        return JSONResponse(status_code=201, content={"id": prompt_id, "task_id": prompt_id, "status": "queued"})

    async def _history(self, service: ServiceConfig, prompt_id: str) -> tuple[dict[str, Any], dict[str, str] | None]:
        timeout = float(service.settings.get("timeout_seconds") or 600)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(join_url(service.base_url, f"/history/{urllib.parse.quote(prompt_id, safe='')}"), headers=self._headers(service))
        response.raise_for_status()
        data = response.json()
        item = data.get(prompt_id) if isinstance(data, dict) else None
        if not isinstance(item, dict):
            return {}, None
        return item, extract_output(item)

    async def query(self, service: ServiceConfig, upstream_task_id: str) -> Response:
        try:
            item, output = await self._history(service, upstream_task_id)
        except httpx.HTTPError as exc:
            return JSONResponse(status_code=502, content={"error": f"ComfyUI history failed: {exc}"})
        if not item:
            return JSONResponse({"id": upstream_task_id, "status": "running"})
        messages = item.get("status", {}).get("messages", []) if isinstance(item.get("status"), dict) else []
        for message in messages if isinstance(messages, list) else []:
            if isinstance(message, list) and message and message[0] == "execution_error":
                detail = message[1] if len(message) > 1 and isinstance(message[1], dict) else {}
                return JSONResponse({"id": upstream_task_id, "status": "failed", "error": detail.get("exception_message") or "ComfyUI execution error"})
        if output:
            return JSONResponse({"id": upstream_task_id, "status": "completed", "output": output})
        return JSONResponse({"id": upstream_task_id, "status": "running"})

    async def download_output(self, service: ServiceConfig, upstream_task_id: str) -> Response:
        item, output = await self._history(service, upstream_task_id)
        if not item or not output:
            return JSONResponse(status_code=409, content={"error": "ComfyUI output is not ready"})
        query = urllib.parse.urlencode(output)
        timeout = float(service.settings.get("timeout_seconds") or 600)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            result = await client.get(join_url(service.base_url, f"/view?{query}"), headers=self._headers(service))
        return Response(content=result.content, status_code=result.status_code, media_type=result.headers.get("content-type", "application/octet-stream"))


def register(registry) -> None:
    registry.register(ComfyUIAdapter())
