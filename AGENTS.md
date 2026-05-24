<!-- Purpose: Agent role definitions and invocation guide for jimAI runs. Date: 2026-03-10 -->
# Agent Roles

## Core Roles
1. `planner`  
   Responsibility: create action plan, dependency-aware workflow, and research-first strategy.
1. `coder`  
   Responsibility: implement file edits, integrations, and tool-driven build actions.
1. `tester`  
   Responsibility: run required checks and report failures with remediation signals.
1. `verifier`  
   Responsibility: gate completion quality and enforce/advise verification outcomes.

## Reliability Controls
1. `strict_verification`  
   Behavior: verifier failures stop run when ON; continue with warning when OFF.
1. `continue_on_subagent_failure`  
   Behavior: non-planner subagent failures continue the run when ON.
1. `subagent_retry_attempts`  
   Behavior: retries failed subagent execution before terminal failure path.

## Model Mapping
Configure in Settings using `agent_models` JSON with keys:
1. `planner`, `coder`, `tester`, `verifier`
1. `role:<role>`
1. `id:<agent-id>`

## Invocation
1. Start run: `POST /api/agent-space/runs/start`
1. Builder launch: `POST /api/agent-space/builder/launch`
1. Configure settings: `POST /api/agent-space/settings`

### Example Run Payload
```json
{
  "objective": "Build feature X with review flow",
  "autonomous": true,
  "review_gate": true,
  "subagent_retry_attempts": 2,
  "continue_on_subagent_failure": true,
  "strict_verification": false
}
```

## Updated Agent Communication Protocol (2026-03-11)

### Handoff Format
When an agent completes a task and hands off to another:
```
HANDOFF {from_agent} -> {to_agent}
Status: complete|partial|blocked
Output: {brief description of what was produced}
Requires: {what the receiving agent needs from this handoff}
Blockers: {any issues the receiving agent should know about}
```

### New Agent Roles Added

#### TEST_AGENT
- **Role**: Frontend unit test author
- **Tools**: Vitest, React Testing Library, jsdom
- **Scope**: frontend/src/**/*.test.{ts,tsx}
- **Input**: Component files and API mocks
- **Output**: Passing test suite, coverage report

#### E2E_AGENT
- **Role**: End-to-end test author
- **Tools**: Playwright (Node)
- **Scope**: e2e/**/*.spec.ts, playwright.config.ts
- **Input**: Running app (backend + frontend)
- **Output**: Smoke tests for critical user flows

#### SECURITY_AGENT
- **Role**: API security hardening
- **Tools**: In-house rate limiter, CSRF middleware, FastAPI Depends
- **Scope**: backend/agent_space/rate_limiter.py, csrf_middleware.py, api.py
- **Output**: Rate limiting on /runs/start, CSRF header validation

#### OBS_AGENT
- **Role**: Observability and metrics
- **Tools**: prometheus-client
- **Scope**: backend/agent_space/metrics.py, main.py /metrics endpoint
- **Output**: Prometheus metrics endpoint at GET /metrics

#### ORCH_AGENT
- **Role**: Orchestrator modularization
- **Tools**: Python refactoring
- **Scope**: backend/agent_space/orchestrator.py, orch_helpers.py, orch_planning.py
- **Output**: Cleaner module boundaries, reduced file sizes

#### DOCS_AGENT
- **Role**: Documentation and configuration templates
- **Scope**: .env.example, README.md, AGENTS.md, COMPLETION_REPORT.md, CHANGELOG.md
- **Output**: Up-to-date documentation with all new features documented

## Autonomy Primitives (2026-05-09)

Five autonomy primitives live in `backend/agent_space/autonomy/`. Each is
independently usable; the orchestrator wires them together.

### EpisodicMemory
- **What**: Persistent (run, agent, event, outcome, summary) records.
- **Index**: nomic-embed-text vectors stored inline (base64 float32).
- **API**: `record`, `search`, `list_by_run`, `list_recent`, `consolidate`.
- **Storage**: `data/agent_space/autonomy/episodes.jsonl`.

### SkillLibrary
- **What**: Verifier-gated capture of winning artifacts (code, action
  sequences, traces) for retrieval against new objectives.
- **API**: `capture`, `retrieve`, `list_all`, `delete`, `render_for_prompt`.
- **Pattern**: Voyager / AutoSkill — compounding capability without
  fine-tuning.

### ReflectionEngine
- **What**: Reflexion-style verbal critique generated after a verifier
  rejection; injected into the next attempt's prompt.
- **API**: `reflect`, `lessons_for(objective)`, `render_for_prompt`.
- **Storage**: `data/agent_space/autonomy/reflections.jsonl`.

### ReplanEngine
- **What**: Mid-run goal re-evaluation. Returns a structured decision
  (`continue` / `replan` / `abort`) plus patches (`drop`,
  `insert_after`, `replace`) applied to the in-flight plan.
- **API**: `evaluate`, `apply_patches`.
- **Pattern**: Magentic-One progress ledger.

### HeartbeatScheduler
- **What**: Tick-driven scheduler that wakes regardless of external
  events. Agents can schedule their own future wake-ups via
  `schedule_self`.
- **API**: `start`, `stop`, `tick`, `add_job`, `update_job`,
  `delete_job`, `schedule_self`, `list_jobs`, `status`.
- **Storage**: `data/agent_space/autonomy/heartbeat_jobs.json`.
- **Toggle**: `settings.heartbeat_enabled` auto-starts the loop on
  boot.

API surface: `/api/autonomy/*` — see `backend/api/autonomy_api.py`.

## Defensive Security Agents (2026-05-09)

Six defensive agents live in `backend/agent_space/security/`. All run
fully local. Wired into the orchestrator via `add_pre_action_hook`.

### PromptShield
- Regex pre-filter for injection / jailbreak patterns + optional
  guardrail-model verdict (Granite Guardian, Llama Guard, ShieldGemma).
- Configure via `shield.use_guardrail_model("granite-guardian:8b")`.

### SecretScanner
- High-confidence regex detector for AWS, GCP, GitHub, OpenAI,
  Slack, Stripe, Twilio keys, JWTs, PEM blocks, generic
  api_key/password assignments, DB connection strings.
- Used by ToolGate before each tool call and standalone via API.

### ToolGate
- PEP enforcing capability allowlist + arg-shape policy + per-(agent,
  tool) rate limit + secret scan on tool args.
- Default policies match the existing action_type vocabulary.

### EgressGuardian
- URL allowlist + PII redaction (email, phone, SSN, credit card,
  IBAN) for outbound traffic.
- Defaults include the 20 domains the platform already fetches.

### BehaviorMonitor
- Per-run heuristic watchdog: iteration cap, wall-clock cap, token
  budget, step dedup, n-gram tool-sequence repeat detector.
- Catches the OWASP Agentic Top-10 "Agentic Resource Exhaustion" class
  without ML.

### SupplyChainSentinel
- pip-audit + npm audit scanner with baseline diff.
- Returns new-since-baseline findings to surface real changes.

API surface: `/api/security/*` — see `backend/api/security_api.py`.

## Self-Improvement Pipeline (2026-05-09)

Three CLI scripts implement the minimum viable continuous self-improvement
loop recommended by 2026 fine-tuning research:

- `scripts/agent_trace_logger.py` — append-only ReAct trace logger with
  daily JSONL files (data/agent_space/autonomy/traces).
- `scripts/agent_eval.py` — tau-bench-inspired lightweight local eval
  with three scripted tasks and mocked tools. Reports
  success_rate, avg_steps_to_success, tool_error_rate.
- `scripts/self_improve_loop.py` — end-to-end pipeline: read recent
  successful traces -> SFT pairs -> Unsloth QLoRA -> agent_eval ->
  promote if delta > 5pp vs frozen baseline.

Designed to be triggered by the heartbeat scheduler as a nightly job.
