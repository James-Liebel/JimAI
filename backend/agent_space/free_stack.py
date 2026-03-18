"""Free-stack integration utilities for Agent Space/jimAI."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import httpx

from .config import SettingsStore
from .paths import DATA_ROOT, PROJECT_ROOT


class FreeStackIntegrationManager:
    """Loads free-stack credentials/endpoints and exposes health + notification helpers."""

    def __init__(self, *, settings_store: SettingsStore) -> None:
        self.settings_store = settings_store

    @staticmethod
    def _parse_env_file(path: Path) -> dict[str, str]:
        if not path.exists():
            return {}
        data: dict[str, str] = {}
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()
        return data

    def _candidate_env_paths(self) -> list[Path]:
        cfg = self.settings_store.get()
        override = str(cfg.get("free_stack_env_path", "") or "").strip()
        candidates: list[Path] = []
        if override:
            candidates.append(Path(override).expanduser())
        candidates.extend(
            [
                DATA_ROOT / "secure" / "free-stack.env",
                PROJECT_ROOT / "data" / "agent_space" / "secure" / "free-stack.env",
                PROJECT_ROOT / "data" / "agent_space" / "runtime" / "free-stack.env",
            ]
        )
        deduped: list[Path] = []
        seen: set[str] = set()
        for path in candidates:
            key = str(path.resolve()) if path.exists() else str(path)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(path)
        return deduped

    def resolve_env_path(self) -> Path:
        for path in self._candidate_env_paths():
            if path.exists():
                return path
        return self._candidate_env_paths()[0]

    def load_env(self) -> tuple[Path, dict[str, str]]:
        env_path = self.resolve_env_path()
        return env_path, self._parse_env_file(env_path)

    @staticmethod
    def _build_service_urls(env: dict[str, str]) -> dict[str, str]:
        def _port(name: str, default: str) -> str:
            value = str(env.get(name, default) or default).strip()
            return value or default

        return {
            "grafana": f"http://localhost:{_port('GRAFANA_PORT', '13000')}",
            "minio_console": f"http://localhost:{_port('MINIO_CONSOLE_PORT', '19001')}",
            "pgadmin": f"http://localhost:{_port('PGADMIN_PORT', '15050')}",
            "redis_commander": f"http://localhost:{_port('REDIS_COMMANDER_PORT', '18081')}",
            "gotify": f"http://localhost:{_port('GOTIFY_PORT', '18080')}",
            "qdrant_dashboard": f"http://localhost:{_port('QDRANT_PORT', '16333')}/dashboard",
            "searxng": f"http://localhost:{_port('SEARXNG_PORT', '18082')}",
            "prometheus": f"http://localhost:{_port('PROMETHEUS_PORT', '19090')}",
            "loki": f"http://localhost:{_port('LOKI_PORT', '13100')}",
            "postgres": f"localhost:{_port('POSTGRES_PORT', '15432')}",
            "redis": f"localhost:{_port('REDIS_PORT', '16379')}",
            "minio_api": f"localhost:{_port('MINIO_API_PORT', '19000')}",
        }

    async def _probe_http(self, url: str, timeout_seconds: float = 3.0) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
                resp = await client.get(url)
            return {"reachable": True, "http_status": int(resp.status_code), "error": ""}
        except Exception as exc:
            return {"reachable": False, "http_status": 0, "error": str(exc)}

    async def status(self, *, include_probe: bool = True) -> dict[str, Any]:
        cfg = self.settings_store.get()
        env_path, env_map = self.load_env()
        urls = self._build_service_urls(env_map)

        gotify_url = str(cfg.get("free_stack_gotify_url", "") or "").strip() or urls.get("gotify", "")
        gotify_token = str(cfg.get("free_stack_gotify_token", "") or "").strip()

        services = [
            {"key": "grafana", "name": "Grafana", "url": urls["grafana"]},
            {"key": "minio_console", "name": "MinIO Console", "url": urls["minio_console"]},
            {"key": "pgadmin", "name": "pgAdmin", "url": urls["pgadmin"]},
            {"key": "redis_commander", "name": "Redis Commander", "url": urls["redis_commander"]},
            {"key": "gotify", "name": "Gotify", "url": urls["gotify"]},
            {"key": "qdrant_dashboard", "name": "Qdrant Dashboard", "url": urls["qdrant_dashboard"]},
            {"key": "searxng", "name": "SearXNG", "url": urls["searxng"]},
            {"key": "prometheus", "name": "Prometheus", "url": urls["prometheus"]},
            {"key": "loki", "name": "Loki", "url": urls["loki"]},
        ]

        if include_probe:
            probed: list[dict[str, Any]] = []
            for row in services:
                probe = await self._probe_http(str(row["url"]))
                probed.append({**row, **probe})
            services = probed

        return {
            "enabled": bool(cfg.get("free_stack_enabled", True)),
            "env_path": str(env_path),
            "env_loaded": bool(env_map),
            "generated_at": time.time(),
            "services": services,
            "infra": {
                "postgres": urls["postgres"],
                "redis": urls["redis"],
                "minio_api": urls["minio_api"],
            },
            "gotify": {
                "enabled": bool(cfg.get("free_stack_gotify_enabled", False)),
                "url": gotify_url,
                "token_configured": bool(gotify_token),
            },
        }

    def sync_settings_from_env(self) -> dict[str, Any]:
        env_path, env_map = self.load_env()
        urls = self._build_service_urls(env_map)
        updates = {
            "free_stack_enabled": True,
            "free_stack_env_path": str(env_path),
            "free_stack_gotify_url": urls.get("gotify", ""),
        }
        return self.settings_store.update(updates)

    async def send_gotify(
        self,
        *,
        title: str,
        message: str,
        priority: int = 5,
    ) -> dict[str, Any]:
        cfg = self.settings_store.get()
        env_path, env_map = self.load_env()
        urls = self._build_service_urls(env_map)
        base_url = str(cfg.get("free_stack_gotify_url", "") or "").strip() or urls.get("gotify", "")
        token = str(cfg.get("free_stack_gotify_token", "") or "").strip()
        if not bool(cfg.get("free_stack_gotify_enabled", False)):
            return {"ok": False, "skipped": True, "error": "Gotify integration is disabled in settings."}
        if not base_url:
            return {"ok": False, "error": "Gotify URL is not configured."}
        if not token:
            return {"ok": False, "error": "Gotify token is not configured."}
        endpoint = f"{base_url.rstrip('/')}/message?token={quote_plus(token)}"
        payload = {
            "title": str(title or "jimAI Notification")[:120],
            "message": str(message or "").strip()[:4000],
            "priority": int(priority),
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(endpoint, data=payload)
            if resp.status_code >= 400:
                return {"ok": False, "error": f"Gotify HTTP {resp.status_code}", "response": resp.text[:800]}
            return {"ok": True, "provider": "gotify", "status_code": int(resp.status_code)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    async def send_phone_notification(
        self,
        *,
        title: str,
        message: str,
        priority: int = 5,
    ) -> dict[str, Any]:
        return await self.send_gotify(title=title, message=message, priority=priority)
