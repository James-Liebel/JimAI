---
name: Security and Guardrails
description: Hardens execution, command policies, and data boundaries.
tags: security, policy, sandbox, validation, auth
complexity: 5
source: system-default
updated_at: 2026-03-12T01:43:55.907822+00:00
---

# Security and Guardrails

Hardens execution, command policies, and data boundaries.

## Mission
- Execute this skill at depth level `5`.
- Optimize for correctness, reversibility, and measurable progress.

## Required Inputs
- Objective text
- Current repository state
- Constraints (security/runtime/performance)

## Workflow
1. Validate all external inputs and constrain risky operations.
2. Avoid secrets in code paths and redact sensitive logs.
3. Apply least-privilege defaults in command and file tooling.
4. Add explicit rejection paths for unsafe user actions.

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