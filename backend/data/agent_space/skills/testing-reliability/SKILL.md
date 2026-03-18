---
name: Testing and Reliability
description: Adds targeted tests, regression checks, and failure recovery.
tags: tests, reliability, qa, regression, retry
complexity: 4
source: system-default
updated_at: 2026-03-12T01:43:55.906607+00:00
---

# Testing and Reliability

Adds targeted tests, regression checks, and failure recovery.

## Mission
- Execute this skill at depth level `4`.
- Optimize for correctness, reversibility, and measurable progress.

## Required Inputs
- Objective text
- Current repository state
- Constraints (security/runtime/performance)

## Workflow
1. Identify highest-risk code paths and add direct test coverage.
2. Validate critical API contracts and state transitions.
3. Add graceful retries or deterministic fallback behavior on failure.
4. Record reproducible validation output for each change.

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