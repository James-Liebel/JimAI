<!-- Purpose: Phase 0 orientation snapshot for full-repo autonomy flow. Date: 2026-03-10 -->
# Orientation Report

## Stack Summary
- Frontend: React + TypeScript + Vite (`frontend/`).
- Backend: FastAPI + Python (`backend/`).
- Model runtime: Ollama local endpoint (`http://localhost:11434`), integrated via `backend/models/ollama_client.py`.
- Data/runtime artifacts: `data/agent_space/*` (reviews, snapshots, logs, memory, index, workflows, teams, exports, runtime, secure).
- Desktop shell: Electron launcher (`desktop/`), lifecycle orchestration via `scripts/agentspace_lifecycle.py`.
- Infra integrations: optional free-stack compose services under `infra/free-stack`.

## Page Inventory
- Working baseline (compiled/present): Dashboard, Builder, Workflow Review, Chat, Research, SelfCode, Agent Browser, Automation, Agent Studio, System Audit, Notebook, Settings.
- Recently hardened:
  - Builder: passes `continue_on_subagent_failure`.
  - Settings: toggle for `continue_on_subagent_failure`; agent model map save/clear behavior improved.
- Validation-backed paths:
  - Build/run/review/apply/rollback/power/export: passing validation script.
  - Team messaging/handoff flow: passing validation script.
  - System audit endpoint behavior: passing validation script.

## API Surface Inventory
- Router root: `/api/agent-space/*` in `backend/agent_space/api.py`.
- Major groups observed:
  - Runtime/system: `status`, `metrics`, `power`, `settings`, `events`.
  - Runs: start/list/get/stop/events/messages.
  - Builder: `clarify`, `launch`, `preview`.
  - Review/snapshots: list/get/approve/reject/apply/undo/commit, rollback, snapshots.
  - Tools: tree/read/write/replace/shell.
  - Teams/subagents: CRUD + team message archive.
  - Browser automation: session lifecycle + navigate/click/type/extract/screenshot/cursor ops.
  - Research/chat/index/memory/export/proactive flows.
  - Automation and optional n8n controls.
  - Free-stack integration status/sync/notify.

## Agent Definitions Inventory
- Core role normalization in orchestrator:
  - `planner`, `coder`, `tester`, `verifier` (with aliases normalized).
- Workflow normalization includes planner-first and verifier-gated structure.
- Team/handoff messaging persisted and queryable through teams/messages APIs.
- Reliability controls available:
  - `strict_verification`
  - `subagent_retry_attempts`
  - `continue_on_subagent_failure` (added in this pass)

## Critical Issues Found
- Repository has substantial existing in-flight edits; full regression scope is broad.
- ChromaDB/Pydantic warning on Python 3.14 remains (non-fatal but important).
- Some runs can still fail due model/runtime prompt variability; improved by failure-continue controls but not eliminated.
- Static audit still reports many LOW-level debug prints and one TODO marker.

## Feature Gaps Identified
- Full-page E2E UI test coverage is incomplete.
- Full hardening of every optional integration path (all free-stack services + optional n8n + browser probes) remains iterative.
- UX simplification and progressive disclosure across all pages can still be tightened.

## Refactor Targets
- Continue splitting large backend router into smaller route modules.
- Expand typed API envelopes consistently for all route groups.
- Reduce frontend bundle size via route-level/code splitting.
- Convert residual debug prints in scripts/tests to structured logging where appropriate.
- Add broader automated tests for UI interaction states and long-running orchestration retries.
