---
name: Zero-Downtime Change Management
description: Ships risky updates using staged rollout, verification, and fast rollback procedures.
tags: rollout, staging, rollback, change-management, safety
complexity: 5
source: system-default
updated_at: 2026-03-12T01:43:55.923963+00:00
---

# Zero-Downtime Change Management

Ships risky updates using staged rollout, verification, and fast rollback procedures.

## Mission
- Execute this skill at depth level `5`.
- Optimize for correctness, reversibility, and measurable progress.

## Required Inputs
- Objective text
- Current repository state
- Constraints (security/runtime/performance)

## Workflow
1. Define rollout phases and success/failure criteria per phase.
2. Gate production promotion on explicit verification checks.
3. Prepare immediate rollback path with state integrity checks.
4. Record release decision log for every production-impacting change.

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