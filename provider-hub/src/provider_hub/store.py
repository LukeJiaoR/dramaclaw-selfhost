from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from provider_hub.models import CAPABILITIES, ResolvedTarget, ServiceConfig, infer_protocol


SCHEMA = """
CREATE TABLE IF NOT EXISTS provider_services (
    id TEXT PRIMARY KEY,
    service_type TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT '',
    protocol TEXT NOT NULL,
    name TEXT NOT NULL,
    base_url TEXT NOT NULL DEFAULT '',
    api_key TEXT NOT NULL DEFAULT '',
    models_json TEXT NOT NULL DEFAULT '[]',
    default_model TEXT NOT NULL DEFAULT '',
    endpoint TEXT NOT NULL DEFAULT '',
    query_endpoint TEXT NOT NULL DEFAULT '',
    priority INTEGER NOT NULL DEFAULT 0,
    is_default INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    settings_json TEXT NOT NULL DEFAULT '{}',
    source TEXT NOT NULL DEFAULT 'manual',
    source_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_provider_services_type
ON provider_services(service_type, is_active, is_default, priority);

CREATE TABLE IF NOT EXISTS capability_bindings (
    capability TEXT PRIMARY KEY,
    service_id TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    FOREIGN KEY(service_id) REFERENCES provider_services(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS model_routes (
    incoming_model TEXT PRIMARY KEY,
    capability TEXT NOT NULL,
    service_id TEXT NOT NULL,
    upstream_model TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    FOREIGN KEY(service_id) REFERENCES provider_services(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS video_tasks (
    id TEXT PRIMARY KEY,
    service_id TEXT NOT NULL,
    upstream_task_id TEXT NOT NULL,
    protocol TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(service_id) REFERENCES provider_services(id) ON DELETE CASCADE
);
"""


class ProviderStore:
    def __init__(self, path: str | Path | None = None):
        data_dir = Path(os.environ.get("PROVIDER_HUB_DATA_DIR", "./data"))
        self.path = Path(path) if path else data_dir / "provider-hub.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _json_object(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if not value:
            return {}
        try:
            parsed = json.loads(str(value))
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _json_list(value: Any) -> list[str]:
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        if not value:
            return []
        try:
            parsed = json.loads(str(value))
        except (TypeError, ValueError):
            parsed = [value]
        if not isinstance(parsed, list):
            parsed = [parsed]
        return [str(item).strip() for item in parsed if str(item).strip()]

    def _row(self, row: sqlite3.Row | None) -> ServiceConfig | None:
        if row is None:
            return None
        return ServiceConfig(
            id=str(row["id"]),
            service_type=str(row["service_type"]),
            provider=str(row["provider"]),
            protocol=str(row["protocol"]),
            name=str(row["name"]),
            base_url=str(row["base_url"]),
            api_key=str(row["api_key"]),
            models=tuple(self._json_list(row["models_json"])),
            default_model=str(row["default_model"]),
            endpoint=str(row["endpoint"]),
            query_endpoint=str(row["query_endpoint"]),
            priority=int(row["priority"]),
            is_default=bool(row["is_default"]),
            is_active=bool(row["is_active"]),
            settings=self._json_object(row["settings_json"]),
            source=str(row["source"]),
            source_id=str(row["source_id"]),
        )

    def list_services(self, service_type: str = "") -> list[ServiceConfig]:
        with self.connect() as conn:
            if service_type:
                rows = conn.execute(
                    "SELECT * FROM provider_services WHERE service_type=? "
                    "ORDER BY is_default DESC, priority DESC, name",
                    (service_type,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM provider_services "
                    "ORDER BY service_type, is_default DESC, priority DESC, name"
                ).fetchall()
        return [item for row in rows if (item := self._row(row)) is not None]

    def get_service(self, service_id: str) -> ServiceConfig | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM provider_services WHERE id=?", (service_id,)
            ).fetchone()
        return self._row(row)

    def save_service(self, data: dict[str, Any], service_id: str = "") -> ServiceConfig:
        now = self._now()
        service_type = str(data.get("service_type") or "text").strip().lower()
        provider = str(data.get("provider") or "openai").strip().lower()
        base_url = str(data.get("base_url") or "").strip().rstrip("/")
        protocol = infer_protocol(
            service_type,
            provider,
            str(data.get("protocol") or data.get("api_protocol") or ""),
            base_url,
        )
        models = self._json_list(data.get("models", data.get("model")))
        default_model = str(data.get("default_model") or (models[0] if models else "")).strip()
        if default_model and default_model not in models:
            models.insert(0, default_model)
        source = str(data.get("source") or "manual").strip() or "manual"
        existing = self.get_service(service_id) if service_id else None
        service_id = service_id or str(uuid.uuid4())
        source_id = str(data.get("source_id") or "").strip() or service_id
        api_key = data.get("api_key")
        if api_key is None and existing:
            api_key = existing.api_key
        values = (
            service_id,
            service_type,
            provider,
            protocol,
            str(data.get("name") or provider or service_type).strip(),
            base_url,
            str(api_key or "").strip(),
            json.dumps(models, ensure_ascii=False),
            default_model,
            str(data.get("endpoint") or "").strip(),
            str(data.get("query_endpoint") or "").strip(),
            int(data.get("priority") or 0),
            1 if data.get("is_default") else 0,
            0 if data.get("is_active") is False else 1,
            json.dumps(self._json_object(data.get("settings")), ensure_ascii=False),
            source,
            source_id,
            now,
            now,
        )
        with self._lock, self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if data.get("is_default"):
                conn.execute(
                    "UPDATE provider_services SET is_default=0 WHERE service_type=? AND id<>?",
                    (service_type, service_id),
                )
            conn.execute(
                """
                INSERT INTO provider_services(
                    id,service_type,provider,protocol,name,base_url,api_key,
                    models_json,default_model,endpoint,query_endpoint,priority,
                    is_default,is_active,settings_json,source,source_id,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    service_type=excluded.service_type,provider=excluded.provider,
                    protocol=excluded.protocol,name=excluded.name,base_url=excluded.base_url,
                    api_key=excluded.api_key,models_json=excluded.models_json,
                    default_model=excluded.default_model,endpoint=excluded.endpoint,
                    query_endpoint=excluded.query_endpoint,priority=excluded.priority,
                    is_default=excluded.is_default,is_active=excluded.is_active,
                    settings_json=excluded.settings_json,source=excluded.source,
                    source_id=excluded.source_id,updated_at=excluded.updated_at
                """,
                values,
            )
            conn.commit()
        saved = self.get_service(service_id)
        if saved is None:
            raise RuntimeError("provider service was not saved")
        return saved

    def find_source_service(self, source: str, source_id: str) -> ServiceConfig | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM provider_services WHERE source=? AND source_id=?",
                (source, source_id),
            ).fetchone()
        return self._row(row)

    def delete_service(self, service_id: str) -> bool:
        with self._lock, self.connect() as conn:
            result = conn.execute("DELETE FROM provider_services WHERE id=?", (service_id,))
            conn.commit()
        return result.rowcount > 0

    def save_binding(self, capability: str, service_id: str, model: str = "") -> None:
        capability = capability.strip().lower()
        if capability not in CAPABILITIES:
            raise ValueError(f"unsupported capability: {capability}")
        service = self.get_service(service_id)
        if service is None:
            raise ValueError("provider service does not exist")
        with self._lock, self.connect() as conn:
            conn.execute(
                "INSERT INTO capability_bindings(capability,service_id,model,updated_at) "
                "VALUES(?,?,?,?) ON CONFLICT(capability) DO UPDATE SET "
                "service_id=excluded.service_id,model=excluded.model,updated_at=excluded.updated_at",
                (capability, service_id, model.strip(), self._now()),
            )
            conn.commit()

    def list_bindings(self) -> dict[str, dict[str, str]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT capability,service_id,model FROM capability_bindings ORDER BY capability"
            ).fetchall()
        return {
            str(row["capability"]): {
                "service_id": str(row["service_id"]),
                "model": str(row["model"]),
            }
            for row in rows
        }

    def save_model_route(
        self, incoming_model: str, capability: str, service_id: str, upstream_model: str
    ) -> None:
        incoming_model = incoming_model.strip()
        if not incoming_model:
            raise ValueError("incoming_model is required")
        if capability not in CAPABILITIES:
            raise ValueError(f"unsupported capability: {capability}")
        if self.get_service(service_id) is None:
            raise ValueError("provider service does not exist")
        with self._lock, self.connect() as conn:
            conn.execute(
                "INSERT INTO model_routes(incoming_model,capability,service_id,upstream_model,updated_at) "
                "VALUES(?,?,?,?,?) ON CONFLICT(incoming_model) DO UPDATE SET "
                "capability=excluded.capability,service_id=excluded.service_id,"
                "upstream_model=excluded.upstream_model,updated_at=excluded.updated_at",
                (incoming_model, capability, service_id, upstream_model.strip(), self._now()),
            )
            conn.commit()

    def delete_model_route(self, incoming_model: str) -> bool:
        with self.connect() as conn:
            result = conn.execute(
                "DELETE FROM model_routes WHERE incoming_model=?", (incoming_model,)
            )
            conn.commit()
        return result.rowcount > 0

    def list_model_routes(self) -> list[dict[str, str]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT incoming_model,capability,service_id,upstream_model "
                "FROM model_routes ORDER BY capability,incoming_model"
            ).fetchall()
        return [dict(row) for row in rows]

    def resolve(self, capability: str, incoming_model: str = "") -> ResolvedTarget:
        capability = capability.strip().lower()
        incoming_model = incoming_model.strip()
        with self.connect() as conn:
            if incoming_model:
                route = conn.execute(
                    "SELECT capability,service_id,upstream_model FROM model_routes "
                    "WHERE incoming_model=?",
                    (incoming_model,),
                ).fetchone()
                if route:
                    service = self.get_service(str(route["service_id"]))
                    if service and service.is_active:
                        return ResolvedTarget(
                            capability=str(route["capability"]),
                            service=service,
                            incoming_model=incoming_model,
                            upstream_model=str(route["upstream_model"]) or service.default_model,
                        )
            binding = conn.execute(
                "SELECT service_id,model FROM capability_bindings WHERE capability=?",
                (capability,),
            ).fetchone()
            if binding:
                service = self.get_service(str(binding["service_id"]))
                if service and service.is_active:
                    return ResolvedTarget(
                        capability=capability,
                        service=service,
                        incoming_model=incoming_model,
                        upstream_model=str(binding["model"]) or service.default_model,
                    )
            row = conn.execute(
                "SELECT * FROM provider_services WHERE service_type=? AND is_active=1 "
                "ORDER BY is_default DESC,priority DESC,name LIMIT 1",
                ("text" if capability == "vision" else capability,),
            ).fetchone()
        service = self._row(row)
        if service is None:
            raise LookupError(f"no active provider configured for capability: {capability}")
        return ResolvedTarget(
            capability=capability,
            service=service,
            incoming_model=incoming_model,
            upstream_model=service.default_model or incoming_model,
        )

    def save_video_task(self, service_id: str, upstream_task_id: str, protocol: str) -> str:
        task_id = str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO video_tasks(id,service_id,upstream_task_id,protocol,created_at) "
                "VALUES(?,?,?,?,?)",
                (task_id, service_id, upstream_task_id, protocol, self._now()),
            )
            conn.commit()
        return task_id

    def get_video_task(self, task_id: str) -> dict[str, str] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM video_tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None
