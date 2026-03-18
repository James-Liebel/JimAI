"""Markdown skill store for Agent Space.

Purpose: manage reusable SKILL.md instructions that can be auto-generated and
selected by objective for planner/verifier orchestration prompts.
Date: 2026-03-11
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models import ollama_client

from .config import SettingsStore
from .paths import SKILLS_DIR, ensure_layout

logger = logging.getLogger(__name__)


def _now() -> float:
    return time.time()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(text: str) -> str:
    raw = re.sub(r"[^a-zA-Z0-9]+", "-", str(text or "").strip().lower()).strip("-")
    return raw or "skill"


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(token) > 2}


def _safe_parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    match = re.search(r"\{.*\}", str(text or ""), flags=re.DOTALL)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
        if isinstance(payload, dict):
            return payload
    except Exception:
        return None
    return None


class SkillStore:
    """Persist and select reusable markdown skills for autonomous runs."""

    _DEFAULT_SKILLS: list[dict[str, Any]] = [
        {
            "name": "Planning Architect",
            "slug": "planning-architect",
            "description": "Creates execution plans, milestones, and dependency-safe delivery strategy.",
            "tags": ["planning", "architecture", "dependencies", "milestones"],
            "complexity": 5,
            "workflow": [
                "Map scope, constraints, and acceptance criteria before writing code.",
                "Break work into parallel-safe tracks with explicit dependencies.",
                "Define risk list and mitigation checks before execution starts.",
                "Output deterministic plan + checkpoints + fallback path.",
            ],
        },
        {
            "name": "Fullstack Implementation",
            "slug": "fullstack-implementation",
            "description": "Implements coherent backend/frontend changes with stable API contracts.",
            "tags": ["backend", "frontend", "api", "integration", "refactor"],
            "complexity": 4,
            "workflow": [
                "Align data contracts and error envelopes before edits.",
                "Implement backend changes with safe defaults and validation.",
                "Wire frontend to APIs with clear loading/error/empty states.",
                "Run fast build/test checks and document behavior changes.",
            ],
        },
        {
            "name": "Research and Source Grounding",
            "slug": "research-source-grounding",
            "description": "Runs broad source discovery and uses evidence before claims.",
            "tags": ["research", "web", "sources", "validation", "facts"],
            "complexity": 4,
            "workflow": [
                "Expand ambiguous queries into multiple high-signal variants.",
                "Collect and deduplicate sources before synthesis.",
                "Prefer primary sources and current data for unstable facts.",
                "Report uncertainty explicitly when confidence is low.",
            ],
        },
        {
            "name": "UX and Product Clarity",
            "slug": "ux-product-clarity",
            "description": "Simplifies UX, improves visual hierarchy, and removes user confusion.",
            "tags": ["ux", "ui", "accessibility", "copy", "product"],
            "complexity": 3,
            "workflow": [
                "Reduce required user decisions and automate low-risk defaults.",
                "Make editable inputs explicit and stateful actions obvious.",
                "Improve spacing, labels, and status feedback for comprehension.",
                "Ensure desktop/mobile usability with no broken interaction paths.",
            ],
        },
        {
            "name": "Testing and Reliability",
            "slug": "testing-reliability",
            "description": "Adds targeted tests, regression checks, and failure recovery.",
            "tags": ["tests", "reliability", "qa", "regression", "retry"],
            "complexity": 4,
            "workflow": [
                "Identify highest-risk code paths and add direct test coverage.",
                "Validate critical API contracts and state transitions.",
                "Add graceful retries or deterministic fallback behavior on failure.",
                "Record reproducible validation output for each change.",
            ],
        },
        {
            "name": "Security and Guardrails",
            "slug": "security-guardrails",
            "description": "Hardens execution, command policies, and data boundaries.",
            "tags": ["security", "policy", "sandbox", "validation", "auth"],
            "complexity": 5,
            "workflow": [
                "Validate all external inputs and constrain risky operations.",
                "Avoid secrets in code paths and redact sensitive logs.",
                "Apply least-privilege defaults in command and file tooling.",
                "Add explicit rejection paths for unsafe user actions.",
            ],
        },
        {
            "name": "Performance Optimizer",
            "slug": "performance-optimizer",
            "description": "Improves latency/throughput, compacts heavy flows, and removes bottlenecks.",
            "tags": ["performance", "latency", "throughput", "optimization", "async"],
            "complexity": 3,
            "workflow": [
                "Measure hot paths and avoid sequential I/O where parallel is safe.",
                "Use bounded timeouts and fallbacks for external dependencies.",
                "Reduce payload size and unnecessary render/update churn.",
                "Document measurable before/after impact.",
            ],
        },
        {
            "name": "Release and Documentation",
            "slug": "release-documentation",
            "description": "Keeps changelogs, runbooks, and capability docs synchronized.",
            "tags": ["docs", "release", "changelog", "runbook", "handoff"],
            "complexity": 2,
            "workflow": [
                "Summarize user-visible behavior changes and migration notes.",
                "Update capability docs with concrete paths and limits.",
                "Capture unresolved risks and next operational steps.",
                "Ensure rollback/undo instructions remain accurate.",
            ],
        },
        {
            "name": "Agentic Parallel Orchestration",
            "slug": "agentic-parallel-orchestration",
            "description": "Designs complex multi-agent plans with controlled parallelism and robust handoffs.",
            "tags": ["agents", "parallel", "orchestration", "handoff", "verification"],
            "complexity": 5,
            "workflow": [
                "Partition objective into independent workstreams with explicit dependency edges.",
                "Define planner, implementers, reviewers, and verifier responsibilities.",
                "Require structured inter-agent messages for assumptions, outputs, and blockers.",
                "Enforce verification gates and fallback routing before completion.",
            ],
        },
        {
            "name": "Prompt and Toolchain Engineering",
            "slug": "prompt-toolchain-engineering",
            "description": "Builds high-signal prompts, tool policies, and deterministic fallback paths for agent execution.",
            "tags": ["prompt", "tools", "llm", "fallback", "determinism"],
            "complexity": 5,
            "workflow": [
                "Constrain prompt contracts with strict output schemas and failure behaviors.",
                "Map which tools are mandatory, optional, or prohibited per objective stage.",
                "Add retry policy with simplified prompts for recoverable failures.",
                "Track action outcomes to continuously tighten prompt quality.",
            ],
        },
        {
            "name": "Distributed Reliability Engineering",
            "slug": "distributed-reliability-engineering",
            "description": "Hardens long-running and multi-service flows against partial failure and degraded dependencies.",
            "tags": ["reliability", "distributed", "retries", "timeouts", "resilience"],
            "complexity": 5,
            "workflow": [
                "Identify failure domains and non-idempotent operations before changes.",
                "Apply per-step timeout, retry budget, and circuit-breaker style guardrails.",
                "Ensure service degradation paths still return useful partial outputs.",
                "Publish failure telemetry and remediation actions with timestamps.",
            ],
        },
        {
            "name": "API Contract Governance",
            "slug": "api-contract-governance",
            "description": "Maintains strict API contracts, versioning discipline, and backward compatibility checks.",
            "tags": ["api", "contracts", "versioning", "schema", "compatibility"],
            "complexity": 4,
            "workflow": [
                "Define and validate request/response envelopes before endpoint edits.",
                "Guard compatibility with explicit additive-only default strategy.",
                "Introduce clear deprecation markers and migration guidance when needed.",
                "Add endpoint-level tests for status codes and shape integrity.",
            ],
        },
        {
            "name": "Data Schema Evolution",
            "slug": "data-schema-evolution",
            "description": "Evolves data models safely with migration-aware patterns and rollback options.",
            "tags": ["data", "schema", "migration", "rollback", "storage"],
            "complexity": 4,
            "workflow": [
                "Document current and target schema with compatibility constraints.",
                "Use two-step migrations when destructive operations are possible.",
                "Add migration validation checks and backfill observability.",
                "Keep rollback path tested for each schema transition.",
            ],
        },
        {
            "name": "Observability and Incident Ops",
            "slug": "observability-incident-ops",
            "description": "Improves diagnostics with metrics/logs/traces and incident-ready operating procedures.",
            "tags": ["observability", "metrics", "logging", "incident", "monitoring"],
            "complexity": 4,
            "workflow": [
                "Define service health indicators and failure thresholds by component.",
                "Instrument critical paths with low-noise, high-signal telemetry.",
                "Create incident triage playbook with first-response checklist.",
                "Capture post-incident lessons as concrete engineering actions.",
            ],
        },
        {
            "name": "Mobile and Interaction Performance",
            "slug": "mobile-interaction-performance",
            "description": "Optimizes mobile UI behavior, touch interactions, and render performance under constrained devices.",
            "tags": ["mobile", "touch", "responsive", "performance", "ux"],
            "complexity": 4,
            "workflow": [
                "Audit viewport layout and interaction affordances for small screens.",
                "Reduce repaint/reflow and avoid long synchronous UI tasks.",
                "Validate form focus, scrolling, and keyboard behavior on mobile.",
                "Keep text contrast and tappable targets consistently accessible.",
            ],
        },
        {
            "name": "Design System Integrity",
            "slug": "design-system-integrity",
            "description": "Enforces coherent visual language, spacing system, and component consistency.",
            "tags": ["design-system", "ui", "consistency", "accessibility", "components"],
            "complexity": 3,
            "workflow": [
                "Consolidate repeated style patterns into reusable component classes.",
                "Enforce spacing/typography tokens for predictable visual rhythm.",
                "Eliminate ambiguous interactive states across forms and buttons.",
                "Validate readability and contrast on all major surfaces.",
            ],
        },
        {
            "name": "Competitive and Market Research",
            "slug": "competitive-market-research",
            "description": "Runs structured competitor and market scans with evidence-backed recommendations.",
            "tags": ["market", "competitive", "research", "pricing", "positioning"],
            "complexity": 4,
            "workflow": [
                "Frame hypotheses and define competitor comparison criteria first.",
                "Gather sources from multiple domains and normalize key facts.",
                "Separate verified evidence from inference in findings.",
                "Translate findings into prioritized product/monetization actions.",
            ],
        },
        {
            "name": "Product Analytics and Experimentation",
            "slug": "product-analytics-experimentation",
            "description": "Establishes event instrumentation, KPI definitions, and experiment execution rigor.",
            "tags": ["analytics", "kpi", "events", "experimentation", "growth"],
            "complexity": 4,
            "workflow": [
                "Define north-star metric and supporting diagnostic metrics.",
                "Map required events and data quality checks before launch.",
                "Specify experiment design, duration, and decision thresholds.",
                "Produce concise result summary with recommended next iteration.",
            ],
        },
        {
            "name": "Cost and Resource Optimization",
            "slug": "cost-resource-optimization",
            "description": "Reduces compute/runtime cost with efficiency controls and budget-aware defaults.",
            "tags": ["cost", "resource", "optimization", "budget", "efficiency"],
            "complexity": 3,
            "workflow": [
                "Identify expensive operations and estimate impact of optimization options.",
                "Apply caching, batching, and bounded timeouts where safe.",
                "Set budget guardrails and fallback behavior for high-cost paths.",
                "Track before/after cost or latency improvements with evidence.",
            ],
        },
        {
            "name": "Zero-Downtime Change Management",
            "slug": "zero-downtime-change-management",
            "description": "Ships risky updates using staged rollout, verification, and fast rollback procedures.",
            "tags": ["rollout", "staging", "rollback", "change-management", "safety"],
            "complexity": 5,
            "workflow": [
                "Define rollout phases and success/failure criteria per phase.",
                "Gate production promotion on explicit verification checks.",
                "Prepare immediate rollback path with state integrity checks.",
                "Record release decision log for every production-impacting change.",
            ],
        },
    ]

    _KEYWORD_SKILL_BOOSTS: dict[str, str] = {
        "mobile": "ux-product-clarity",
        "responsive": "ux-product-clarity",
        "touch": "mobile-interaction-performance",
        "research": "research-source-grounding",
        "search": "research-source-grounding",
        "web": "research-source-grounding",
        "market": "competitive-market-research",
        "competitor": "competitive-market-research",
        "pricing": "competitive-market-research",
        "price": "research-source-grounding",
        "security": "security-guardrails",
        "auth": "security-guardrails",
        "token": "security-guardrails",
        "policy": "security-guardrails",
        "test": "testing-reliability",
        "verification": "testing-reliability",
        "retry": "testing-reliability",
        "incident": "observability-incident-ops",
        "metrics": "observability-incident-ops",
        "monitoring": "observability-incident-ops",
        "latency": "performance-optimizer",
        "slow": "performance-optimizer",
        "perf": "performance-optimizer",
        "cost": "cost-resource-optimization",
        "budget": "cost-resource-optimization",
        "optimize": "cost-resource-optimization",
        "ui": "ux-product-clarity",
        "ux": "ux-product-clarity",
        "frontend": "fullstack-implementation",
        "backend": "fullstack-implementation",
        "api": "fullstack-implementation",
        "schema": "data-schema-evolution",
        "migration": "data-schema-evolution",
        "contract": "api-contract-governance",
        "plan": "planning-architect",
        "agent": "planning-architect",
        "workflow": "planning-architect",
        "parallel": "agentic-parallel-orchestration",
        "orchestration": "agentic-parallel-orchestration",
        "prompt": "prompt-toolchain-engineering",
        "tool": "prompt-toolchain-engineering",
        "rollout": "zero-downtime-change-management",
        "downtime": "zero-downtime-change-management",
        "release": "release-documentation",
        "docs": "release-documentation",
    }

    def __init__(self, *, settings_store: SettingsStore) -> None:
        ensure_layout()
        self._settings = settings_store
        self._cache: dict[str, dict[str, Any]] = {}
        self.install_default_skills()

    def _skill_dir(self, slug: str) -> Path:
        return SKILLS_DIR / slug

    def _skill_md(self, slug: str) -> Path:
        return self._skill_dir(slug) / "SKILL.md"

    def _meta_path(self, slug: str) -> Path:
        return self._skill_dir(slug) / "skill.json"

    @staticmethod
    def _parse_frontmatter(raw_text: str) -> tuple[dict[str, str], str]:
        text = str(raw_text or "")
        if not text.startswith("---\n"):
            return {}, text
        marker = "\n---\n"
        end = text.find(marker, 4)
        if end < 0:
            return {}, text
        header = text[4:end].splitlines()
        body = text[end + len(marker):]
        parsed: dict[str, str] = {}
        for row in header:
            if ":" not in row:
                continue
            key, value = row.split(":", 1)
            parsed[str(key).strip().lower()] = str(value).strip()
        return parsed, body

    @staticmethod
    def _render_markdown(
        *,
        name: str,
        description: str,
        tags: list[str],
        complexity: int,
        source: str,
        workflow: list[str],
        extra_notes: str = "",
    ) -> str:
        safe_tags = [tag for tag in [str(t).strip() for t in tags] if tag]
        steps = [f"{idx}. {row}" for idx, row in enumerate(workflow[:8], start=1)]
        if not steps:
            steps = [
                "1. Analyze objective and constraints.",
                "2. Propose safe plan with acceptance criteria.",
                "3. Execute with validation and fallback behavior.",
            ]
        notes = str(extra_notes or "").strip()
        header = [
            "---",
            f"name: {name.strip()}",
            f"description: {' '.join(description.strip().split())}",
            f"tags: {', '.join(safe_tags)}",
            f"complexity: {max(1, min(int(complexity), 5))}",
            f"source: {source.strip() or 'custom'}",
            f"updated_at: {_iso_now()}",
            "---",
            "",
            f"# {name.strip()}",
            "",
            description.strip(),
            "",
            "## Mission",
            f"- Execute this skill at depth level `{max(1, min(int(complexity), 5))}`.",
            "- Optimize for correctness, reversibility, and measurable progress.",
            "",
            "## Required Inputs",
            "- Objective text",
            "- Current repository state",
            "- Constraints (security/runtime/performance)",
            "",
            "## Workflow",
            *steps,
            "",
            "## Quality Gates",
            "- Validate outputs against objective and acceptance criteria.",
            "- Report unresolved risks explicitly before completion.",
            "- Prefer deterministic fallbacks over silent failure.",
            "",
            "## Output Contract",
            "- Deliver concrete actions with files/endpoints/components impacted.",
            "- Include verification evidence (build/test/log checks).",
            "- Include rollback/undo strategy for risky changes.",
            "",
            "## Failure Recovery",
            "- If primary method fails, retry with reduced scope once.",
            "- If still failing, switch strategy and record why.",
            "- Never suppress errors; surface them with actionable next step.",
            "",
        ]
        if notes:
            header.extend(["## Notes", notes, ""])
        return "\n".join(header).strip() + "\n"

    def _summary(self, skill: dict[str, Any]) -> dict[str, Any]:
        return {
            "slug": str(skill.get("slug", "")),
            "name": str(skill.get("name", "")),
            "description": str(skill.get("description", "")),
            "tags": list(skill.get("tags") or []),
            "complexity": int(skill.get("complexity") or 1),
            "source": str(skill.get("source", "custom")),
            "created_at": float(skill.get("created_at") or 0.0),
            "updated_at": float(skill.get("updated_at") or 0.0),
        }

    def _read_skill(self, slug: str) -> dict[str, Any] | None:
        md_path = self._skill_md(slug)
        meta_path = self._meta_path(slug)
        if not md_path.exists():
            return None
        try:
            raw_md = md_path.read_text(encoding="utf-8")
        except Exception:
            return None
        frontmatter, body = self._parse_frontmatter(raw_md)
        meta: dict[str, Any] = {}
        if meta_path.exists():
            try:
                loaded = json.loads(meta_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    meta = loaded
            except Exception:
                meta = {}
        tags_text = str(frontmatter.get("tags", "")).strip()
        tags = [row.strip() for row in tags_text.split(",") if row.strip()]
        if not tags:
            tags = [str(row).strip() for row in list(meta.get("tags") or []) if str(row).strip()]
        skill = {
            "slug": slug,
            "name": str(frontmatter.get("name") or meta.get("name") or slug),
            "description": str(frontmatter.get("description") or meta.get("description") or ""),
            "tags": tags,
            "complexity": int(frontmatter.get("complexity") or meta.get("complexity") or 1),
            "source": str(frontmatter.get("source") or meta.get("source") or "custom"),
            "created_at": float(meta.get("created_at") or md_path.stat().st_ctime),
            "updated_at": float(meta.get("updated_at") or md_path.stat().st_mtime),
            "metadata": dict(meta.get("metadata") or {}),
            "content": body.strip(),
            "raw_markdown": raw_md,
            "path": str(md_path),
        }
        self._cache[slug] = dict(skill)
        return skill

    def _resolve_slug(self, name_or_slug: str) -> str | None:
        raw = str(name_or_slug or "").strip()
        if not raw:
            return None
        slug = _slugify(raw)
        if self._skill_md(slug).exists():
            return slug
        for row in self.list_skills(limit=5000):
            if str(row.get("slug")) == slug:
                return slug
            if str(row.get("name", "")).strip().lower() == raw.lower():
                return str(row.get("slug"))
        return None

    def list_skills(self, *, limit: int = 200) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for skill_dir in SKILLS_DIR.glob("*"):
            if not skill_dir.is_dir():
                continue
            slug = str(skill_dir.name)
            loaded = self._read_skill(slug)
            if loaded is None:
                continue
            rows.append(self._summary(loaded))
        rows.sort(key=lambda row: float(row.get("updated_at") or 0.0), reverse=True)
        return rows[: max(1, int(limit))]

    def get_skill(self, name_or_slug: str) -> dict[str, Any] | None:
        slug = self._resolve_slug(name_or_slug)
        if not slug:
            return None
        cached = self._cache.get(slug)
        if cached is not None:
            return dict(cached)
        return self._read_skill(slug)

    def upsert_skill(
        self,
        *,
        name: str,
        description: str,
        content: str,
        tags: list[str] | None = None,
        complexity: int = 2,
        source: str = "custom",
        metadata: dict[str, Any] | None = None,
        slug: str | None = None,
    ) -> dict[str, Any]:
        skill_name = str(name or "").strip() or "Untitled Skill"
        skill_slug = str(slug or _slugify(skill_name)).strip()
        safe_tags = [str(tag).strip() for tag in list(tags or []) if str(tag).strip()]
        notes = ""
        if metadata:
            tags_from_meta = [str(tag).strip() for tag in list(metadata.get("tags") or []) if str(tag).strip()]
            if tags_from_meta:
                safe_tags.extend(tags_from_meta)
            if isinstance(metadata.get("notes"), str):
                notes = str(metadata.get("notes") or "").strip()
        dedup_tags: list[str] = []
        for tag in safe_tags:
            low = tag.lower()
            if low in {row.lower() for row in dedup_tags}:
                continue
            dedup_tags.append(tag)
        existing = self._read_skill(skill_slug)
        created_at = float(existing.get("created_at") or _now()) if existing else _now()
        final_content = str(content or "").strip()
        if not final_content:
            final_content = self._render_markdown(
                name=skill_name,
                description=description,
                tags=dedup_tags,
                complexity=complexity,
                source=source,
                workflow=[],
                extra_notes=notes,
            )
        elif not final_content.startswith("---\n"):
            final_content = self._render_markdown(
                name=skill_name,
                description=description,
                tags=dedup_tags,
                complexity=complexity,
                source=source,
                workflow=[],
                extra_notes=notes + ("\n\n" + final_content if final_content else ""),
            )

        skill_dir = self._skill_dir(skill_slug)
        skill_dir.mkdir(parents=True, exist_ok=True)
        self._skill_md(skill_slug).write_text(final_content, encoding="utf-8")
        meta_payload = {
            "slug": skill_slug,
            "name": skill_name,
            "description": description.strip(),
            "tags": dedup_tags,
            "complexity": max(1, min(int(complexity), 5)),
            "source": str(source or "custom"),
            "created_at": created_at,
            "updated_at": _now(),
            "metadata": dict(metadata or {}),
        }
        self._meta_path(skill_slug).write_text(json.dumps(meta_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        loaded = self._read_skill(skill_slug)
        if loaded is None:
            raise RuntimeError(f"Failed to load skill '{skill_slug}' after write.")
        return loaded

    def delete_skill(self, name_or_slug: str) -> bool:
        slug = self._resolve_slug(name_or_slug)
        if not slug:
            return False
        self._cache.pop(slug, None)
        skill_dir = self._skill_dir(slug)
        if not skill_dir.exists():
            return False
        shutil.rmtree(skill_dir, ignore_errors=True)
        return True

    def install_default_skills(self) -> list[dict[str, Any]]:
        installed: list[dict[str, Any]] = []
        for row in self._DEFAULT_SKILLS:
            default_slug = str(row.get("slug") or "").strip()
            if default_slug and self._skill_md(default_slug).exists():
                existing = self._read_skill(default_slug)
                if existing is not None:
                    installed.append(self._summary(existing))
                    continue
            workflow = [str(step).strip() for step in list(row.get("workflow") or []) if str(step).strip()]
            md = self._render_markdown(
                name=str(row.get("name") or ""),
                description=str(row.get("description") or ""),
                tags=[str(tag).strip() for tag in list(row.get("tags") or []) if str(tag).strip()],
                complexity=int(row.get("complexity") or 2),
                source="system-default",
                workflow=workflow,
            )
            saved = self.upsert_skill(
                name=str(row.get("name") or ""),
                description=str(row.get("description") or ""),
                content=md,
                tags=[str(tag).strip() for tag in list(row.get("tags") or []) if str(tag).strip()],
                complexity=int(row.get("complexity") or 2),
                source="system-default",
                metadata={"preset": True},
                slug=default_slug,
            )
            installed.append(self._summary(saved))
        return installed

    async def _llm_skill_ideas(self, objective: str, *, max_items: int) -> list[dict[str, Any]]:
        model = str(self._settings.get().get("model", "qwen2.5-coder:14b"))
        prompt = (
            "Generate practical reusable engineering SKILLS for this objective.\n"
            "Return strict JSON object only with key 'skills' where each skill has:\n"
            "name, description, tags (array), workflow (array of 3-6 short steps), complexity (1-5).\n"
            f"Limit to at most {max(1, int(max_items))} skills.\n\n"
            f"Objective:\n{objective.strip()}"
        )
        try:
            text = await asyncio.wait_for(
                ollama_client.chat_full(
                    model=model,
                    messages=[
                        {"role": "system", "content": "Return strict JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                ),
                timeout=8,
            )
        except Exception:
            return []
        parsed = _safe_parse_json_object(text) or {}
        raw_skills = parsed.get("skills")
        if not isinstance(raw_skills, list):
            return []
        rows: list[dict[str, Any]] = []
        for row in raw_skills:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            description = str(row.get("description") or "").strip()
            if not name or not description:
                continue
            tags = [str(tag).strip() for tag in list(row.get("tags") or []) if str(tag).strip()]
            workflow = [str(step).strip() for step in list(row.get("workflow") or []) if str(step).strip()]
            complexity = int(row.get("complexity") or 3)
            rows.append(
                {
                    "name": name,
                    "description": description,
                    "tags": tags,
                    "workflow": workflow,
                    "complexity": max(1, min(complexity, 5)),
                    "source": "llm-auto",
                }
            )
            if len(rows) >= max(1, int(max_items)):
                break
        return rows

    def _heuristic_skill_ideas(self, objective: str, *, max_items: int) -> list[dict[str, Any]]:
        text = str(objective or "").strip()
        if not text:
            return []
        ideas: list[dict[str, Any]] = []
        if any(token in text.lower() for token in ("startup", "growth", "profit", "business", "market")):
            ideas.append(
                {
                    "name": "Growth Experiments and Monetization",
                    "description": "Designs rapid market tests, pricing loops, and measurable growth experiments.",
                    "tags": ["growth", "monetization", "pricing", "experiments", "analytics"],
                    "workflow": [
                        "Define one acquisition hypothesis and one monetization hypothesis.",
                        "Specify instrumentation events before launching experiments.",
                        "Set stop/go criteria and follow-up plan by metric thresholds.",
                    ],
                    "complexity": 4,
                    "source": "heuristic-auto",
                }
            )
        if any(token in text.lower() for token in ("agent", "orchestration", "workflow", "parallel")):
            ideas.append(
                {
                    "name": "Multi-Agent Coordination",
                    "description": "Defines role contracts, handoff protocol, and conflict resolution for parallel agents.",
                    "tags": ["agents", "orchestration", "parallel", "handoff", "verification"],
                    "workflow": [
                        "Assign planner, workers, and verifier with dependency graph.",
                        "Require message contract for handoff and verification channels.",
                        "Enforce completion gates before terminal status.",
                    ],
                    "complexity": 5,
                    "source": "heuristic-auto",
                }
            )
        if any(token in text.lower() for token in ("mobile", "phone", "responsive", "touch")):
            ideas.append(
                {
                    "name": "Mobile Interaction Quality",
                    "description": "Ensures mobile-first interaction quality, readable layout, and touch-safe controls.",
                    "tags": ["mobile", "responsive", "touch", "accessibility", "layout"],
                    "workflow": [
                        "Check all critical controls on narrow viewport constraints.",
                        "Ensure text contrast and form readability across light/dark inputs.",
                        "Validate scroll, focus, and keyboard behavior on mobile screens.",
                    ],
                    "complexity": 3,
                    "source": "heuristic-auto",
                }
            )
        return ideas[: max(1, int(max_items))]

    async def auto_add_for_objective(self, objective: str, *, limit: int = 3) -> list[dict[str, Any]]:
        clean_objective = " ".join(str(objective or "").strip().split())
        if not clean_objective:
            return []
        # Always keep core defaults available.
        if len(self.list_skills(limit=5000)) < len(self._DEFAULT_SKILLS):
            self.install_default_skills()

        target = max(1, min(int(limit), 10))
        created: list[dict[str, Any]] = []
        llm_ideas = await self._llm_skill_ideas(clean_objective, max_items=target)
        heuristic_ideas = self._heuristic_skill_ideas(clean_objective, max_items=target)
        for idea in [*llm_ideas, *heuristic_ideas]:
            if len(created) >= target:
                break
            name = str(idea.get("name") or "").strip()
            if not name:
                continue
            slug = _slugify(name)
            if self._skill_md(slug).exists():
                continue
            description = str(idea.get("description") or "").strip()
            tags = [str(tag).strip() for tag in list(idea.get("tags") or []) if str(tag).strip()]
            workflow = [str(step).strip() for step in list(idea.get("workflow") or []) if str(step).strip()]
            complexity = int(idea.get("complexity") or 3)
            md = self._render_markdown(
                name=name,
                description=description,
                tags=tags,
                complexity=complexity,
                source=str(idea.get("source") or "auto"),
                workflow=workflow,
                extra_notes=f"Auto-generated from objective: {clean_objective[:500]}",
            )
            saved = self.upsert_skill(
                name=name,
                description=description,
                content=md,
                tags=tags,
                complexity=complexity,
                source=str(idea.get("source") or "auto"),
                metadata={"auto_generated": True, "objective": clean_objective[:1500]},
                slug=slug,
            )
            created.append(self._summary(saved))
        return created

    def select_for_objective(self, objective: str, *, limit: int = 8) -> list[dict[str, Any]]:
        clean_objective = " ".join(str(objective or "").strip().split())
        if not clean_objective:
            return []
        objective_tokens = _tokenize(clean_objective)
        all_skills = [self.get_skill(str(row.get("slug"))) for row in self.list_skills(limit=5000)]
        rows = [row for row in all_skills if isinstance(row, dict)]
        scored: list[tuple[float, dict[str, Any]]] = []
        keyword_boost_targets: set[str] = set()
        for token in objective_tokens:
            boost_slug = self._KEYWORD_SKILL_BOOSTS.get(token)
            if boost_slug:
                keyword_boost_targets.add(boost_slug)
        for skill in rows:
            text_blob = " ".join(
                [
                    str(skill.get("name") or ""),
                    str(skill.get("description") or ""),
                    " ".join(str(tag) for tag in list(skill.get("tags") or [])),
                    str(skill.get("content") or "")[:2200],
                ]
            )
            skill_tokens = _tokenize(text_blob)
            overlap = len(objective_tokens & skill_tokens)
            base_score = float(overlap) / float(max(len(objective_tokens), 1))
            complexity_boost = float(skill.get("complexity") or 1) * 0.02
            slug = str(skill.get("slug") or "")
            keyword_boost = 0.35 if slug in keyword_boost_targets else 0.0
            required_boost = 0.1 if slug in {"planning-architect", "testing-reliability"} else 0.0
            total = base_score + complexity_boost + keyword_boost + required_boost
            scored.append((total, skill))
        scored.sort(key=lambda row: row[0], reverse=True)
        selected: list[dict[str, Any]] = []
        for score, skill in scored:
            if score <= 0 and selected:
                continue
            candidate = dict(skill)
            candidate["match_score"] = round(float(score), 4)
            selected.append(candidate)
            if len(selected) >= max(1, min(int(limit), 20)):
                break
        return selected

    def build_context(self, skills: list[dict[str, Any]], *, max_chars: int = 12000) -> str:
        lines: list[str] = []
        for row in list(skills or []):
            name = str(row.get("name") or row.get("slug") or "Skill").strip()
            desc = str(row.get("description") or "").strip()
            tags = [str(tag).strip() for tag in list(row.get("tags") or []) if str(tag).strip()]
            content = str(row.get("content") or "").strip()
            compact_content = re.sub(r"\n{3,}", "\n\n", content)
            if len(compact_content) > 1400:
                compact_content = compact_content[:1400] + "\n...(truncated)"
            lines.append(
                "\n".join(
                    [
                        f"[SKILL] {name}",
                        f"Description: {desc}",
                        f"Tags: {', '.join(tags)}",
                        "Instructions:",
                        compact_content,
                        "",
                    ]
                ).strip()
            )
        text = "\n\n".join(lines).strip()
        if len(text) > max(500, int(max_chars)):
            text = text[: max(500, int(max_chars))] + "\n...(skill context truncated)"
        return text
