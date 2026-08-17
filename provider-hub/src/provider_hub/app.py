from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from provider_hub import __version__
from provider_hub.adapters.video import extract_task_id, normalize_task
from provider_hub.importer import import_localminidrama
from provider_hub.models import CAPABILITIES, ServiceConfig
from provider_hub.registry import load_builtin_adapters
from provider_hub.store import ProviderStore


logging.basicConfig(level=os.environ.get("PROVIDER_HUB_LOG_LEVEL", "INFO"))
logger = logging.getLogger("provider_hub")
store = ProviderStore()
adapters = load_builtin_adapters()
app = FastAPI(title="DramaClaw Provider Hub", version=__version__)
STATIC_DIR = Path(__file__).with_name("static")


class ServiceBody(BaseModel):
    service_type: str
    provider: str = "openai"
    protocol: str = ""
    name: str
    base_url: str = ""
    api_key: str | None = None
    models: list[str] = Field(default_factory=list)
    default_model: str = ""
    endpoint: str = ""
    query_endpoint: str = ""
    priority: int = 0
    is_default: bool = False
    is_active: bool = True
    settings: dict[str, Any] = Field(default_factory=dict)


class BindingBody(BaseModel):
    service_id: str
    model: str = ""


class ModelRouteBody(BaseModel):
    incoming_model: str
    capability: str
    service_id: str
    upstream_model: str = ""


def save_service_and_routes(data: dict[str, Any], service_id: str = "") -> ServiceConfig:
    protocol = str(data.get("protocol") or "").strip().lower()
    if protocol in {"comfyui", "comfyui_native"}:
        if str(data.get("service_type") or "").strip().lower() != "video":
            raise ValueError("native ComfyUI services must use the video service type")
        if not str(data.get("base_url") or "").strip():
            raise ValueError("ComfyUI Base URL is required")
        settings = data.get("settings") if isinstance(data.get("settings"), dict) else {}
        workflows = settings.get("workflows")
        if not isinstance(workflows, list) or not workflows:
            raise ValueError("at least one ComfyUI workflow is required")
        seen: set[str] = set()
        for route in workflows:
            route_id = str(route.get("id") or "").strip() if isinstance(route, dict) else ""
            workflow = route.get("workflow") if isinstance(route, dict) else None
            if not route_id or route_id in seen:
                raise ValueError("ComfyUI workflow IDs must be present and unique")
            seen.add(route_id)
            if not isinstance(workflow, dict) or not workflow or not any(
                isinstance(node, dict) and ("class_type" in node or "inputs" in node)
                for node in workflow.values()
            ):
                raise ValueError(f"ComfyUI workflow {route_id} must use API Format JSON")
    service = store.save_service(data, service_id)
    if service.protocol not in {"comfyui", "comfyui_native"}:
        return service
    wanted = set(service.models)
    for route in store.list_model_routes():
        if route["service_id"] == service.id and route["capability"] == "video" and route["incoming_model"] not in wanted:
            store.delete_model_route(route["incoming_model"])
    for model in wanted:
        store.save_model_route(model, "video", service.id, model)
    return service


def public_service(service: ServiceConfig) -> dict[str, Any]:
    return {
        "id": service.id,
        "service_type": service.service_type,
        "provider": service.provider,
        "protocol": service.protocol,
        "name": service.name,
        "base_url": service.base_url,
        "api_key_configured": bool(service.api_key),
        "api_key_preview": (
            f"{service.api_key[:4]}...{service.api_key[-4:]}"
            if len(service.api_key) > 10
            else "*" * len(service.api_key)
        ),
        "models": list(service.models),
        "default_model": service.default_model,
        "endpoint": service.endpoint,
        "query_endpoint": service.query_endpoint,
        "priority": service.priority,
        "is_default": service.is_default,
        "is_active": service.is_active,
        "settings": service.settings,
        "source": service.source,
        "source_id": service.source_id,
    }


def capability_for_chat(payload: dict[str, Any]) -> str:
    model = str(payload.get("model") or "").lower()
    if "vision" in model:
        return "vision"
    for message in payload.get("messages") or []:
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, list) and any(
            isinstance(item, dict)
            and str(item.get("type") or "") in {"image_url", "input_image", "image"}
            for item in content
        ):
            return "vision"
    return "text"


def require_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail="JSON object required")
    return value


async def dispatch(
    request: Request,
    capability: str,
    operation: str,
    payload: dict[str, Any],
) -> Response:
    try:
        target = store.resolve(capability, str(payload.get("model") or ""))
        adapter = adapters.get(target.service.protocol)
        return await adapter.invoke(
            target=target,
            operation=operation,
            payload=payload,
            request=request,
        )
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.middleware("http")
async def optional_api_key(request: Request, call_next):
    expected = os.environ.get("PROVIDER_HUB_API_KEY", "").strip()
    if expected and request.url.path.startswith("/v1/"):
        supplied = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if supplied != expected:
            return JSONResponse(status_code=401, content={"error": "invalid provider hub key"})
    return await call_next(request)


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {"ok": True, "version": __version__, "protocols": adapters.protocols()}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/api/state")
async def api_state() -> dict[str, Any]:
    return {
        "services": [public_service(item) for item in store.list_services()],
        "bindings": store.list_bindings(),
        "routes": store.list_model_routes(),
        "capabilities": sorted(CAPABILITIES),
        "protocols": adapters.protocols(),
    }


@app.post("/api/services")
async def create_service(body: ServiceBody) -> dict[str, Any]:
    try:
        return public_service(save_service_and_routes(body.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/services/{service_id}")
async def update_service(service_id: str, body: ServiceBody) -> dict[str, Any]:
    if store.get_service(service_id) is None:
        raise HTTPException(status_code=404, detail="service not found")
    try:
        return public_service(save_service_and_routes(body.model_dump(), service_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/services/{service_id}")
async def delete_service(service_id: str) -> dict[str, bool]:
    if not store.delete_service(service_id):
        raise HTTPException(status_code=404, detail="service not found")
    return {"ok": True}


@app.put("/api/bindings/{capability}")
async def update_binding(capability: str, body: BindingBody) -> dict[str, bool]:
    try:
        store.save_binding(capability, body.service_id, body.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/api/routes")
async def create_model_route(body: ModelRouteBody) -> dict[str, bool]:
    try:
        store.save_model_route(
            body.incoming_model,
            body.capability,
            body.service_id,
            body.upstream_model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@app.delete("/api/routes/{incoming_model}")
async def delete_model_route(incoming_model: str) -> dict[str, bool]:
    return {"ok": store.delete_model_route(incoming_model)}


@app.post("/api/import/localminidrama")
async def import_localminidrama_db(file: UploadFile = File(...)) -> dict[str, int]:
    suffix = Path(file.filename or "providers.db").suffix or ".db"
    with tempfile.NamedTemporaryFile(suffix=suffix) as target:
        while chunk := await file.read(1024 * 1024):
            target.write(chunk)
        target.flush()
        try:
            return import_localminidrama(target.name, store)
        except (FileNotFoundError, sqlite3.Error) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/models")
async def models() -> dict[str, Any]:
    ids = {route["incoming_model"] for route in store.list_model_routes()}
    for service in store.list_services():
        ids.update(service.models)
    return {"object": "list", "data": [{"id": item, "object": "model"} for item in sorted(ids)]}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Response:
    payload = require_payload(await request.json())
    return await dispatch(request, capability_for_chat(payload), "chat_completions", payload)


@app.post("/v1/embeddings")
async def embeddings(request: Request) -> Response:
    payload = require_payload(await request.json())
    return await dispatch(request, "embedding", "embeddings", payload)


@app.post("/v1/images/generations")
async def images_generations(request: Request) -> Response:
    payload = require_payload(await request.json())
    return await dispatch(request, "image", "images_generations", payload)


@app.post("/v1/images/edits")
async def images_edits(request: Request) -> Response:
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        raise HTTPException(
            status_code=501,
            detail="multipart image edits require a dedicated adapter",
        )
    payload = require_payload(await request.json())
    return await dispatch(request, "image", "images_edits", payload)


@app.post("/v1/audio/speech")
async def audio_speech(request: Request) -> Response:
    payload = require_payload(await request.json())
    return await dispatch(request, "tts", "audio_speech", payload)


@app.post("/v1/video/generations")
async def video_submit(request: Request) -> Response:
    payload = require_payload(await request.json())
    try:
        target = store.resolve("video", str(payload.get("model") or ""))
        adapter = adapters.get(target.service.protocol)
        response = await adapter.invoke(
            target=target,
            operation="video_submit",
            payload=payload,
            request=request,
        )
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if response.status_code < 200 or response.status_code >= 300:
        return response
    try:
        data = json.loads(response.body)
        upstream_task_id = extract_task_id(data)
    except (TypeError, ValueError):
        upstream_task_id = ""
    if not upstream_task_id:
        return Response(
            content=response.body,
            status_code=502,
            media_type="application/json",
        )
    task_id = store.save_video_task(
        target.service.id, upstream_task_id, target.service.protocol
    )
    return JSONResponse({"id": task_id, "task_id": task_id, "status": "queued"})


@app.get("/v1/video/generations/{task_id}")
async def video_poll(task_id: str) -> Response:
    task = store.get_video_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="video task not found")
    service = store.get_service(task["service_id"])
    if service is None:
        raise HTTPException(status_code=410, detail="video provider was removed")
    adapter = adapters.get(task["protocol"])
    if not hasattr(adapter, "query"):
        raise HTTPException(status_code=501, detail="video adapter does not support polling")
    response = await adapter.query(service, task["upstream_task_id"])
    if response.status_code < 200 or response.status_code >= 300:
        return response
    try:
        data = normalize_task(json.loads(response.body))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"invalid video status response: {exc}") from exc
    data["id"] = task_id
    data["task_id"] = task_id
    data["provider_task_id"] = task["upstream_task_id"]
    if data.get("status") == "completed" and task["protocol"] in {"comfyui", "comfyui_native"}:
        data["video_url"] = f"http://localhost:18001/v1/video/generations/{task_id}/content"
    return JSONResponse(data)


@app.get("/v1/video/generations/{task_id}/content")
async def video_content(task_id: str) -> Response:
    task = store.get_video_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="video task not found")
    service = store.get_service(task["service_id"])
    if service is None:
        raise HTTPException(status_code=410, detail="video provider was removed")
    adapter = adapters.get(task["protocol"])
    if not hasattr(adapter, "download_output"):
        raise HTTPException(status_code=501, detail="video adapter does not proxy output")
    return await adapter.download_output(service, task["upstream_task_id"])


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/app.js")
async def app_js() -> FileResponse:
    return FileResponse(STATIC_DIR / "app.js", media_type="application/javascript")


@app.get("/styles.css")
async def styles_css() -> FileResponse:
    return FileResponse(STATIC_DIR / "styles.css", media_type="text/css")


def main() -> None:
    import uvicorn

    uvicorn.run("provider_hub.app:app", host="0.0.0.0", port=18001)


if __name__ == "__main__":
    main()
