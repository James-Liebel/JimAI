"""Open-source local workflow store and runner (no n8n runtime required)."""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

import httpx

from models import ollama_client

from .config import SettingsStore
from .paths import WORKFLOWS_DIR, ensure_layout
from .web_research import fetch_web, search_web


def _now() -> float:
    return time.time()


def _safe_text(value: Any, *, max_len: int = 4000) -> str:
    text = str(value if value is not None else "").strip()
    if len(text) > max_len:
        return text[:max_len]
    return text


def _normalize_kind(raw_kind: str, raw_type: str, params: dict[str, Any]) -> str:
    kind = str(raw_kind or "").strip().lower()
    node_type = str(raw_type or "").strip().lower()
    if kind in {"trigger", "action", "logic", "ai", "integration", "research"}:
        return kind
    if "webhook" in node_type or "cron" in node_type or "trigger" in node_type:
        return "trigger"
    if node_type.endswith(".if") or node_type.startswith("jimai.logic"):
        return "logic"
    if "ollama" in node_type or node_type.startswith("jimai.ai"):
        return "ai"
    if node_type.startswith("jimai.research"):
        return "research"
    if "httprequest" in node_type:
        url = str(params.get("url") or "").lower()
        if "localhost:11434" in url or "/api/chat" in url:
            return "ai"
        return "integration"
    return "action"


def _extract_nodes_and_edges(graph: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    nodes_raw = list(graph.get("nodes") or [])
    if not isinstance(nodes_raw, list):
        nodes_raw = []
    edges_raw = list(graph.get("edges") or [])
    if not isinstance(edges_raw, list):
        edges_raw = []

    nodes: list[dict[str, Any]] = []
    name_to_id: dict[str, str] = {}

    for idx, raw in enumerate(nodes_raw):
        if not isinstance(raw, dict):
            continue
        node_id = _safe_text(raw.get("id") or f"node-{idx + 1}", max_len=120)
        label = _safe_text(raw.get("label") or raw.get("name") or node_id, max_len=180)
        node_type = _safe_text(raw.get("type") or raw.get("nodeType") or "jimai.action.transform", max_len=240)
        raw_kind = _safe_text(raw.get("kind"), max_len=40)
        params = raw.get("parameters") if isinstance(raw.get("parameters"), dict) else {}
        config = raw.get("config") if isinstance(raw.get("config"), dict) else {}
        if params and "parameters" not in config:
            config = dict(config)
            config["parameters"] = params
        kind = _normalize_kind(raw_kind, node_type, params)

        position_raw = raw.get("position")
        pos_x = 0.0
        pos_y = 0.0
        if isinstance(position_raw, list) and len(position_raw) >= 2:
            pos_x = float(position_raw[0] or 0.0)
            pos_y = float(position_raw[1] or 0.0)
        elif isinstance(position_raw, dict):
            pos_x = float(position_raw.get("x") or 0.0)
            pos_y = float(position_raw.get("y") or 0.0)

        node = {
            "id": node_id,
            "label": label,
            "type": node_type,
            "kind": kind,
            "description": _safe_text(raw.get("description") or raw.get("notes"), max_len=800),
            "position": {"x": pos_x, "y": pos_y},
            "config": config,
        }
        nodes.append(node)
        if label:
            name_to_id.setdefault(label, node_id)

    edges: list[dict[str, str]] = []
    for idx, raw in enumerate(edges_raw):
        if not isinstance(raw, dict):
            continue
        source = _safe_text(raw.get("source"), max_len=120)
        target = _safe_text(raw.get("target"), max_len=120)
        if not source or not target:
            continue
        edge_id = _safe_text(raw.get("id") or f"edge-{idx + 1}", max_len=120)
        edges.append({"id": edge_id, "source": source, "target": target})

    connections = graph.get("connections")
    if isinstance(connections, dict):
        for source_name, payload in connections.items():
            source_id = name_to_id.get(str(source_name), "")
            if not source_id:
                continue
            mains = payload.get("main") if isinstance(payload, dict) else None
            if not isinstance(mains, list):
                continue
            for branch in mains:
                if not isinstance(branch, list):
                    continue
                for link in branch:
                    if not isinstance(link, dict):
                        continue
                    target_name = _safe_text(link.get("node"), max_len=180)
                    target_id = name_to_id.get(target_name, "")
                    if not target_id:
                        continue
                    edges.append(
                        {
                            "id": _safe_text(link.get("id") or f"{source_id}-{target_id}-{len(edges) + 1}", max_len=120),
                            "source": source_id,
                            "target": target_id,
                        }
                    )

    dedup: dict[tuple[str, str], dict[str, str]] = {}
    for edge in edges:
        key = (edge["source"], edge["target"])
        if key not in dedup:
            dedup[key] = edge
    edges = list(dedup.values())

    return nodes, edges


class WorkflowStore:
    """Persistent open workflow store with a lightweight local runner."""

    def __init__(self, *, settings_store: SettingsStore) -> None:
        ensure_layout()
        self._settings = settings_store
        self._cache: dict[str, dict[str, Any]] = {}

    def _path(self, workflow_id: str) -> Path:
        return WORKFLOWS_DIR / f"{workflow_id}.json"

    def status(self) -> dict[str, Any]:
        rows = self.list_workflows(limit=2000)
        return {
            "engine": "jimai-open-workflow",
            "open_source": True,
            "requires_n8n_runtime": False,
            "workflow_count": len(rows),
            "last_updated_at": max([float(row.get("updated_at") or 0.0) for row in rows], default=0.0),
            "public_sources": self.public_sources(),
        }

    def public_sources(self) -> list[dict[str, str]]:
        return [
            {
                "name": "n8n",
                "url": "https://github.com/n8n-io/n8n",
                "license": "Sustainable Use License",
                "why": "Popular workflow UX patterns and node concepts.",
            },
            {
                "name": "Node-RED",
                "url": "https://github.com/node-red/node-red",
                "license": "Apache-2.0",
                "why": "Open visual automation model and deploy flows.",
            },
            {
                "name": "Activepieces",
                "url": "https://github.com/activepieces/activepieces",
                "license": "MIT",
                "why": "Modern open-source automation product patterns.",
            },
            {
                "name": "Automatisch",
                "url": "https://github.com/automatisch/automatisch",
                "license": "AGPL-3.0",
                "why": "Self-hosted workflow automation architecture ideas.",
            },
            {
                "name": "React Flow",
                "url": "https://github.com/xyflow/xyflow",
                "license": "MIT",
                "why": "Core open-source graph canvas UI used by jimAI.",
            },
        ]

    def templates(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "Market Research -> Ollama Brief",
                "description": "Run a search query, fetch top page, summarize with local model.",
                "category": "research",
                "public_sources": self.public_sources(),
                "graph": {
                    "schema": "jimai.workflow.v1",
                    "name": "Market Research Brief",
                    "notes": "Open-source local workflow template.",
                    "nodes": [
                        {
                            "id": "trigger-1",
                            "label": "Manual Trigger",
                            "kind": "trigger",
                            "type": "jimai.trigger.manual",
                            "position": {"x": 60, "y": 80},
                            "config": {"payload_mode": "passthrough"},
                        },
                        {
                            "id": "research-1",
                            "label": "Web Search",
                            "kind": "research",
                            "type": "jimai.research.search",
                            "position": {"x": 320, "y": 80},
                            "config": {"query": "best micro saas ideas", "limit": 5},
                        },
                        {
                            "id": "ai-1",
                            "label": "Ollama Summary",
                            "kind": "ai",
                            "type": "jimai.ai.ollama",
                            "position": {"x": 600, "y": 80},
                            "config": {
                                "model": "qwen2.5-coder:14b",
                                "prompt": "Summarize key opportunities from this research payload:\n{input_json}",
                            },
                        },
                    ],
                    "edges": [
                        {"id": "e1", "source": "trigger-1", "target": "research-1"},
                        {"id": "e2", "source": "research-1", "target": "ai-1"},
                    ],
                },
            },
            {
                "name": "Input -> Logic Gate -> Integration Webhook",
                "description": "Conditionally post payloads to an external endpoint.",
                "category": "integration",
                "public_sources": self.public_sources(),
                "graph": {
                    "schema": "jimai.workflow.v1",
                    "name": "Conditional Webhook",
                    "notes": "Open-source local workflow template.",
                    "nodes": [
                        {
                            "id": "trigger-1",
                            "label": "Manual Trigger",
                            "kind": "trigger",
                            "type": "jimai.trigger.manual",
                            "position": {"x": 80, "y": 80},
                            "config": {},
                        },
                        {
                            "id": "logic-1",
                            "label": "Has Message?",
                            "kind": "logic",
                            "type": "jimai.logic.condition",
                            "position": {"x": 360, "y": 80},
                            "config": {"field": "message", "operation": "is_not_empty"},
                        },
                        {
                            "id": "http-1",
                            "label": "Send Webhook",
                            "kind": "integration",
                            "type": "jimai.integration.http",
                            "position": {"x": 660, "y": 80},
                            "config": {
                                "url": "https://example.com/webhook",
                                "method": "POST",
                                "include_input": True,
                            },
                        },
                    ],
                    "edges": [
                        {"id": "e1", "source": "trigger-1", "target": "logic-1"},
                        {"id": "e2", "source": "logic-1", "target": "http-1"},
                    ],
                },
            },
        ]

    def list_workflows(self, limit: int = 200) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in WORKFLOWS_DIR.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            wf_id = str(data.get("id") or "").strip()
            if not wf_id:
                continue
            self._cache[wf_id] = dict(data)
            rows.append(
                {
                    "id": wf_id,
                    "name": str(data.get("name") or "Untitled Workflow"),
                    "description": str(data.get("description") or ""),
                    "tags": list(data.get("tags") or []),
                    "created_at": float(data.get("created_at") or 0.0),
                    "updated_at": float(data.get("updated_at") or 0.0),
                    "last_run_at": float(data.get("last_run_at") or 0.0),
                    "last_run_status": str(data.get("last_run_status") or ""),
                }
            )
        rows.sort(key=lambda row: row.get("updated_at") or 0.0, reverse=True)
        return rows[: max(1, limit)]

    def get_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        cached = self._cache.get(workflow_id)
        if cached is not None:
            return dict(cached)
        path = self._path(workflow_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        self._cache[workflow_id] = dict(data)
        return dict(data)

    def save_workflow(
        self,
        *,
        workflow_id: str | None,
        name: str,
        description: str = "",
        graph: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        public_sources: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        existing = self.get_workflow(workflow_id) if workflow_id else None
        now = _now()
        final_id = workflow_id or str(uuid.uuid4())
        payload = {
            "id": final_id,
            "name": _safe_text(name or "Untitled Workflow", max_len=200),
            "description": _safe_text(description, max_len=2000),
            "graph": graph if isinstance(graph, dict) else {},
            "tags": [str(tag).strip() for tag in list(tags or []) if str(tag).strip()],
            "public_sources": list(public_sources or self.public_sources()),
            "created_at": float(existing.get("created_at") if existing else now),
            "updated_at": now,
            "last_run_at": float(existing.get("last_run_at") if existing else 0.0),
            "last_run_status": str(existing.get("last_run_status") if existing else ""),
            "last_run_summary": dict(existing.get("last_run_summary") if existing else {}),
        }
        self._write(final_id, payload)
        return dict(payload)

    def delete_workflow(self, workflow_id: str) -> bool:
        self._cache.pop(workflow_id, None)
        path = self._path(workflow_id)
        if not path.exists():
            return False
        path.unlink(missing_ok=True)
        return True

    def clear(self) -> int:
        removed = 0
        for path in WORKFLOWS_DIR.glob("*.json"):
            try:
                path.unlink(missing_ok=True)
                removed += 1
            except Exception:
                continue
        self._cache = {}
        return removed

    async def run_workflow(
        self,
        workflow_id: str,
        *,
        input_payload: dict[str, Any] | None = None,
        max_steps: int = 120,
        continue_on_error: bool = False,
    ) -> dict[str, Any]:
        workflow = self.get_workflow(workflow_id)
        if workflow is None:
            raise FileNotFoundError(f"Workflow '{workflow_id}' not found.")
        graph = workflow.get("graph") if isinstance(workflow.get("graph"), dict) else {}
        nodes, edges = _extract_nodes_and_edges(graph)
        if not nodes:
            raise ValueError("Workflow graph has no nodes.")

        node_by_id = {str(node["id"]): node for node in nodes}
        outgoing: dict[str, list[str]] = {node_id: [] for node_id in node_by_id}
        incoming_count: dict[str, int] = {node_id: 0 for node_id in node_by_id}
        for edge in edges:
            source = str(edge.get("source") or "")
            target = str(edge.get("target") or "")
            if source not in node_by_id or target not in node_by_id:
                continue
            outgoing[source].append(target)
            incoming_count[target] += 1

        roots = [node_id for node_id, count in incoming_count.items() if count == 0]
        trigger_roots = [node["id"] for node in nodes if str(node.get("kind")) == "trigger"]
        queue: list[str] = trigger_roots or roots or [nodes[0]["id"]]
        queue = [str(node_id) for node_id in queue if str(node_id) in node_by_id]
        seen_steps = 0
        run_input = dict(input_payload or {})
        outputs: dict[str, dict[str, Any]] = {}
        events: list[dict[str, Any]] = []
        errors: list[str] = []

        while queue and seen_steps < max(1, int(max_steps)):
            node_id = queue.pop(0)
            node = node_by_id.get(node_id)
            if not node:
                continue
            seen_steps += 1

            merged_input = dict(run_input)
            for source_id, targets in outgoing.items():
                if node_id in targets:
                    if source_id in outputs and isinstance(outputs[source_id], dict):
                        merged_input.update(outputs[source_id])

            started_at = _now()
            try:
                result = await self._execute_node(node, merged_input)
                duration_ms = int((_now() - started_at) * 1000)
                outputs[node_id] = dict(result)
                events.append(
                    {
                        "timestamp": _now(),
                        "node_id": node_id,
                        "label": node.get("label"),
                        "kind": node.get("kind"),
                        "status": "ok",
                        "duration_ms": duration_ms,
                        "output": result,
                    }
                )
                should_continue = not (
                    str(node.get("kind")) == "logic" and not bool(result.get("_condition_result", True))
                )
                if should_continue:
                    queue.extend([target for target in outgoing.get(node_id, []) if target in node_by_id])
            except Exception as exc:
                duration_ms = int((_now() - started_at) * 1000)
                message = f"{node.get('label') or node_id}: {exc}"
                errors.append(message)
                events.append(
                    {
                        "timestamp": _now(),
                        "node_id": node_id,
                        "label": node.get("label"),
                        "kind": node.get("kind"),
                        "status": "error",
                        "duration_ms": duration_ms,
                        "error": str(exc),
                    }
                )
                if continue_on_error:
                    queue.extend([target for target in outgoing.get(node_id, []) if target in node_by_id])
                    continue
                break

        exhausted = seen_steps >= int(max_steps)
        status = "completed"
        if errors:
            status = "completed_with_errors" if continue_on_error else "failed"
        elif exhausted and queue:
            status = "max_steps_reached"

        summary = {
            "status": status,
            "events": len(events),
            "errors": len(errors),
            "steps": seen_steps,
            "max_steps": int(max_steps),
            "last_node_output": outputs.get(events[-1]["node_id"], {}) if events else {},
        }
        workflow["last_run_at"] = _now()
        workflow["last_run_status"] = status
        workflow["last_run_summary"] = summary
        workflow["updated_at"] = _now()
        self._write(str(workflow["id"]), workflow)

        return {
            "workflow_id": workflow.get("id"),
            "workflow_name": workflow.get("name"),
            "status": status,
            "summary": summary,
            "errors": errors,
            "events": events,
            "output": outputs,
        }

    async def _execute_node(self, node: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        kind = str(node.get("kind") or "action")
        config = node.get("config") if isinstance(node.get("config"), dict) else {}
        params = config.get("parameters") if isinstance(config.get("parameters"), dict) else {}
        merged_cfg = dict(config)
        for key, value in params.items():
            merged_cfg.setdefault(key, value)

        if kind == "trigger":
            return {"triggered": True, **payload}

        if kind == "action":
            result = dict(payload)
            updates = merged_cfg.get("set") if isinstance(merged_cfg.get("set"), dict) else {}
            if not updates:
                values = merged_cfg.get("values") if isinstance(merged_cfg.get("values"), dict) else {}
                string_rows = values.get("string") if isinstance(values.get("string"), list) else []
                for row in string_rows:
                    if not isinstance(row, dict):
                        continue
                    name = _safe_text(row.get("name"), max_len=120)
                    if not name:
                        continue
                    result[name] = row.get("value")
            else:
                result.update(updates)
            note = _safe_text(merged_cfg.get("note"), max_len=400)
            if note:
                result["_note"] = note
            return result

        if kind == "logic":
            field = _safe_text(merged_cfg.get("field"), max_len=120) or "message"
            operation = _safe_text(merged_cfg.get("operation"), max_len=120).lower() or "is_not_empty"
            expected = merged_cfg.get("value")
            value = payload.get(field)
            if operation == "equals":
                ok = value == expected
            elif operation == "contains":
                ok = str(expected or "") in str(value or "")
            elif operation == "is_empty":
                ok = not bool(value)
            else:
                ok = bool(value)
            return {**payload, "_condition_field": field, "_condition_result": bool(ok)}

        if kind == "research":
            query = _safe_text(merged_cfg.get("query") or payload.get("query"), max_len=300)
            if not query:
                query = "latest software startup opportunities"
            limit = int(merged_cfg.get("limit") or 5)
            search = await search_web(query, limit=max(1, min(10, limit)))
            first_url = ""
            if bool(search.get("ok")):
                rows = list(search.get("results") or [])
                if rows:
                    first_url = _safe_text(rows[0].get("url"), max_len=700)
            fetched: dict[str, Any] = {}
            if first_url:
                fetched = await fetch_web(first_url, max_chars=8000)
            return {
                **payload,
                "research_query": query,
                "research_results": search.get("results", []),
                "research_offline": bool(search.get("offline")),
                "fetched_page": fetched,
            }

        if kind == "ai":
            settings = self._settings.get()
            model = _safe_text(merged_cfg.get("model") or settings.get("model") or "qwen2.5-coder:14b", max_len=120)
            prompt_template = _safe_text(
                merged_cfg.get("prompt") or "Analyze this workflow payload and return concise next-step guidance:\n{input_json}",
                max_len=12000,
            )
            rendered = prompt_template.replace("{input_json}", json.dumps(payload, ensure_ascii=False, indent=2)[:14000])
            content = await ollama_client.chat_full(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a local workflow AI node. Be concise and structured."},
                    {"role": "user", "content": rendered},
                ],
                temperature=0.2,
            )
            return {**payload, "ai_model": model, "ai_output": _safe_text(content, max_len=20000)}

        if kind == "integration":
            url = _safe_text(merged_cfg.get("url"), max_len=700)
            method = _safe_text(merged_cfg.get("method") or "POST", max_len=20).upper()
            timeout_seconds = float(merged_cfg.get("timeout_seconds") or 20.0)
            include_input = bool(merged_cfg.get("include_input", True))
            body = merged_cfg.get("body") if isinstance(merged_cfg.get("body"), dict) else {}
            request_json = dict(body)
            if include_input:
                request_json["input"] = payload
            if not url:
                return {**payload, "integration_skipped": True, "reason": "url_missing"}
            async with httpx.AsyncClient(timeout=max(2.0, min(timeout_seconds, 90.0)), follow_redirects=True) as client:
                response = await client.request(method, url, json=request_json)
            response_payload: Any
            try:
                response_payload = response.json()
            except Exception:
                response_payload = _safe_text(response.text, max_len=4000)
            return {
                **payload,
                "integration_url": url,
                "integration_status": int(response.status_code),
                "integration_ok": response.status_code < 400,
                "integration_response": response_payload,
            }

        return {**payload, "_warning": f"Unsupported kind '{kind}', passthrough applied."}

    def _write(self, workflow_id: str, payload: dict[str, Any]) -> None:
        path = self._path(workflow_id)
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        try:
            path.write_text(text, encoding="utf-8")
        except Exception:
            logger.warning("Failed to write workflow %s to disk", workflow_id, exc_info=True)
        self._cache[workflow_id] = dict(payload)
