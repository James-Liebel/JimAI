<!-- Purpose: Phase-0 audit report for jimAI web search rebuild. Date: 2026-03-10 -->
# SEARCH AUDIT REPORT

## Stack Summary
- Backend: FastAPI (Python), async `httpx`, Ollama local API, Qdrant HTTP API.
- Frontend: React + TypeScript + Vite.
- Streaming: SSE endpoints for research and chat.

## Current Flow (Before Rebuild)
1. Query entered via Research/Chat UI.
2. Backend called legacy search/fetch utilities (primarily single-source style behavior).
3. Limited/no deep page reading in core chat path.
4. Inconsistent fallback behavior when sources failed.
5. No robust semantic memory layer for research answers.

## What Was Broken / Slow / Missing
- Query rewrite and retrieval strategy not fully aligned to multi-source live research flow.
- Missing consistent parallel source fan-out + dedup + ranked consolidation.
- Page-content deep fetch was not consistently used for synthesis context.
- Qdrant semantic cache was not fully integrated in the research stream pipeline.
- Cache-hit latency remained high due full pipeline overhead on repeated queries.
- Service health probing lacked Qdrant auth header support.
- Research UI lacked full step-by-step pipeline progress and memory-hit behavior.

## Files Audited
- `backend/agent_space/web_research.py`
- `backend/agent_space/api_routes_chat_research.py`
- `backend/agent_space/runtime.py`
- `backend/api/chat.py`
- `frontend/src/pages/Research.tsx`
- `frontend/src/lib/agentSpaceApi.ts`
- `infra/free-stack/docker-compose.yml`
- `scripts/agentspace_lifecycle.py`
- `backend/agent_space/free_stack.py`

## Files Modified During Rebuild
- `backend/agent_space/web_research.py`
- `backend/agent_space/api_routes_chat_research.py`
- `backend/agent_space/runtime.py`
- `backend/api/chat.py`
- `frontend/src/pages/Research.tsx`
- `frontend/src/lib/agentSpaceApi.ts`
- `infra/free-stack/docker-compose.yml`
- `scripts/agentspace_lifecycle.py`
- `backend/agent_space/free_stack.py`
- `backend/tests/agent_space_research_pipeline_validation.py`
- `SEARCH_TEST_RESULTS.md`

## Rebuild Outcome
- Added query rewrite, parallel multi-source search, deep fetch, streaming synthesis, and semantic cache flow.
- Added resilient fallbacks (including raw-mode synthesis fallback and provider error capture).
- Added Qdrant collection bootstrap, lookup/store, and service auth-aware status probing.
- Added exact-query fast memory path to reduce repeat-query latency.
- Added Research SSE UI orchestration states, service badges, source chips, memory-hit banner, and streaming render.

## Constraints Observed in Local Validation Environment
- SearXNG and DDG were offline/unreachable in this run context.
- Pipeline remained functional and returned explicit fallback answers with provider diagnostics.
- Qdrant and Ollama paths were healthy.
