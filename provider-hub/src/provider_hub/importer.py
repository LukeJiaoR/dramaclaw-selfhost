from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from provider_hub.store import ProviderStore


def _settings(value: object) -> dict:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _models(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, ValueError):
        parsed = [value] if value else []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _docker_url(value: str, rewrite_localhost: bool) -> str:
    if not rewrite_localhost or not value:
        return value
    parts = urlsplit(value)
    if parts.hostname not in {"127.0.0.1", "localhost"}:
        return value
    host = "host.docker.internal"
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))


def import_localminidrama(
    source_db: str | Path,
    store: ProviderStore,
    *,
    rewrite_localhost: bool | None = None,
) -> dict[str, int]:
    source_db = Path(source_db)
    if not source_db.is_file():
        raise FileNotFoundError(f"LocalMiniDrama database not found: {source_db}")
    if rewrite_localhost is None:
        rewrite_localhost = os.environ.get("PROVIDER_HUB_DOCKER", "") == "1"
    conn = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM ai_service_configs WHERE deleted_at IS NULL ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    created = 0
    updated = 0
    defaults: dict[str, str] = {}
    for row in rows:
        source_id = str(row["id"])
        existing = store.find_source_service("localminidrama", source_id)
        service = store.save_service(
            {
                "service_type": row["service_type"],
                "provider": row["provider"],
                "api_protocol": row["api_protocol"],
                "name": row["name"],
                "base_url": _docker_url(str(row["base_url"] or ""), rewrite_localhost),
                "api_key": row["api_key"],
                "models": _models(row["model"]),
                "default_model": row["default_model"],
                "endpoint": row["endpoint"],
                "query_endpoint": row["query_endpoint"],
                "priority": row["priority"],
                "is_default": bool(row["is_default"]),
                "is_active": bool(row["is_active"]),
                "settings": _settings(row["settings"]),
                "source": "localminidrama",
                "source_id": source_id,
            },
            existing.id if existing else "",
        )
        if existing:
            updated += 1
        else:
            created += 1
        if service.is_default:
            defaults[service.service_type] = service.id

    for capability in ("text", "image", "storyboard_image", "video", "tts"):
        if service_id := defaults.get(capability):
            service = store.get_service(service_id)
            store.save_binding(capability, service_id, service.default_model if service else "")
    if service_id := defaults.get("text"):
        service = store.get_service(service_id)
        store.save_binding("vision", service_id, service.default_model if service else "")
    return {"created": created, "updated": updated, "total": len(rows)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Import LocalMiniDrama provider configs")
    parser.add_argument("source_db")
    parser.add_argument("--target-db", default="")
    parser.add_argument("--rewrite-localhost", action="store_true")
    args = parser.parse_args()
    store = ProviderStore(args.target_db or None)
    result = import_localminidrama(
        args.source_db,
        store,
        rewrite_localhost=args.rewrite_localhost,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
