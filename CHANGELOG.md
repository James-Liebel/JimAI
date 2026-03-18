<!-- Purpose: Track notable changes to jimAI repository. Date: 2026-03-11 -->
# Changelog

## 2026-03-11

### Added
- `/health` endpoint with multi-service checks: Ollama, ChromaDB, Qdrant (3s timeout each).
- `POST /api/agent-space/runs/stop-all` — bulk-stop all running runs.
- `GET /api/agent-space/settings/history` — read settings change audit trail.
- `frontend/src/components/ErrorBoundary.tsx` — React Error Boundary with Reload button.
- Settings audit log: every settings change appended to `data/agent_space/settings_audit.jsonl`.
- Run filtering: `GET /api/agent-space/runs?status=&limit=&offset=` pagination support.
- New env vars (with defaults) in `backend/config/settings.py`: `N8N_BASE_URL`, `QDRANT_BASE_URL`,
  `SEARXNG_BASE_URL`, `JUPYTER_BASE_URL`, `GRAFANA_BASE_URL`.

### Changed
- All 100+ frontend `fetch()` calls now use `fetchWithTimeout` (30s/60s/120s depending on endpoint).
- Research page: cancel button (aborts SSE), animated step labels, Try Again on error.
- Chat session sidebar: debounced search input (200ms, case-insensitive match on title+preview).
- Dashboard: retry button on error, "last updated X seconds ago" label, connection-lost banner.
- SystemAudit: color-coded status dots (green/amber/red/gray), last-checked timestamps per check.
- Settings: JSON validation on agentModels textarea, inline error, save button disabled when invalid.
- Builder launch button: spinner + "Launching..." text, disabled during pending request.
- Speed mode tooltips updated with clear explanations for Fast / Balanced / Deep.
- `RunStartRequest.objective` in api.py now has `min_length=1`, `max_length=10000` Pydantic validation.
- `SEARXNG_BASE_URL` env var now read first in `web_research._searxng_url()`.
- 30+ bare `except: pass` handlers in agent_space modules replaced with `logger.exception()` /
  `logger.warning(..., exc_info=True)` calls across: browser_agent, api, automation_runtime,
  instance_lifecycle, log_store, memory_index, orchestrator, power, proactive, runtime,
  web_research, workflow_engine.
- `ErrorBoundary` wraps the full `<BrowserRouter>` tree in `main.tsx`.

## 2026-03-10

### Added
- `continue_on_subagent_failure` run/setting control across backend + UI.
- static audit script: `scripts/repo_audit_static.py`.
- generated auditor report: `docs/AUDITOR_ISSUES.md`.
- delivery docs: `COMPLETION_REPORT.md`, `AGENTS.md`.
- one-command phase validator: `scripts/run_all_phases_validation.py`.
- planner auto-recovery validation: `backend/tests/agent_space_planner_recovery_validation.py`.

### Changed
- Research pipeline rebuild (Phase 0-5):
  - query rewrite now uses bounded timeout with fast fallback.
  - parallel search now runs SearXNG, DDG, legacy internal search, and Wikipedia concurrently.
  - deep page fetch now falls back to top merged results if SearXNG is unavailable.
  - SSE research stream now emits step-by-step progress, sources, memory-hit metadata, and provider errors.
  - Qdrant service probe now uses API-key auth headers and reports healthy status correctly.
  - added exact-query fast memory path for near-instant repeated queries in active runtime.
  - cache miss fallback answers are persisted into Qdrant + local exact cache for subsequent reuse.
- Search reliability and observability:
  - provider errors are returned in fallback completion payloads.
  - research timings now include query rewrite, cache check, parallel search, page fetch, synthesis, and total duration.
- Orchestrator failure policy:
  - verifier errors no longer hard-stop when strict verification is OFF.
  - non-planner subagent failures can continue when configured.
  - planner failures now trigger deterministic recovery planning and continue instead of hard-failing.
- Orchestrator latency/reliability hardening:
  - planner now uses deterministic fast-path for explicit non-autonomous team workflows (no blocking model call).
  - verifier now uses deterministic local verification for explicit non-autonomous team workflows.
  - planner/verifier model calls now have bounded timeout windows with fallback output.
  - deterministic file objectives now skip autonomous self-learning unless `force_self_learning` is set.
- Ollama client now retries transient stream and request failures.
- Web research now caches search/fetch results and serves stale cache on offline failures.
- Settings now sanitizes `agent_models` and supports clearing the map with `{}`.
- Data directory bootstrap now ensures `secure`, `generated`, and `self_improvement`.
- Chat live-data reliability:
  - current-data prompts now perform deeper fetch on top search results.
  - stale "knowledge cutoff" style responses are auto-corrected with live source snippets.
  - routing metadata now includes `auto_web_research_fetched_pages` and `stale_response_corrected`.
- Builder UX:
  - added `Simple` (default) vs `Advanced` mode toggle in Build page.
  - simplified default view to prompt/build/run monitoring only.
  - moved terminal/export/manual orchestration controls behind `Advanced`.
  - improved editable-field clarity with explicit `(Editable)` labels.
  - improved Build page scroll behavior for long run/event sessions.
- Workflow Review + SelfCode UX:
  - added `Simple` (default) vs `Advanced` mode toggle to both pages.
  - hid advanced controls (commit/deep summaries/direct-run/apply-all/undo/review diff detail) behind `Advanced`.
  - kept core approve/apply/stop/live-monitor controls in default view.
- Desktop lifecycle reliability:
  - startup now verifies backend/frontend TCP readiness before reporting success.
  - lifecycle now fails fast with actionable reason when child processes exit early.
  - desktop launch now checks for immediate Electron startup failure.
  - frontend startup now falls back to static `dist` serving if Vite dev startup is blocked/fails.

### Validation
- `backend/tests/agent_space_research_pipeline_validation.py` passed and regenerated `SEARCH_TEST_RESULTS.md`.
- Cache-repeat behavior now returns near-instant responses through exact memory path (`~0.002s` in local validation).
- Backend import sanity passed.
- Agent Space core/team/system-audit validation scripts passed.
- Full phase validation runner passed.
- Frontend production build passed.
- Added validation scripts:
  - `backend/tests/agent_space_chat_live_lookup_validation.py`
  - `backend/tests/agent_space_continue_on_failure_validation.py`
  - `backend/tests/agent_space_planner_recovery_validation.py`
