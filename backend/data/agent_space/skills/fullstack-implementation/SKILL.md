---
name: Fullstack Implementation
description: Implements coherent backend/frontend changes with stable API contracts.
tags: backend, frontend, api, integration, refactor
complexity: 4
source: system-default
updated_at: 2026-03-12T01:43:55.901820+00:00
---

# Fullstack Implementation

Implements coherent backend/frontend changes with stable API contracts.

## Mission
- Execute this skill at depth level `4`.
- Optimize for correctness, reversibility, and measurable progress.

## Required Inputs
- Objective text
- Current repository state
- Constraints (security/runtime/performance)

## Workflow
1. Align data contracts and error envelopes before edits.
2. Implement backend changes with safe defaults and validation.
3. Wire frontend to APIs with clear loading/error/empty states.
4. Run fast build/test checks and document behavior changes.

## Quality Gates
- Validate outputs against objective and acceptance criteria.
- Report unresolved risks explicitly before completion.
- Prefer deterministic fallbacks over silent failure.

## Output Contract
- Deliver concrete actions with files/endpoints/components impacted.
- Include verification evidence (build/test/log checks).
- Include rollback/undo strategy for risky changes.

## Failure Recovery
- If primary method fails, retry with reduced scope once.
- If still failing, switch strategy and record why.
- Never suppress errors; surface them with actionable next step.