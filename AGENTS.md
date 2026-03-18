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
