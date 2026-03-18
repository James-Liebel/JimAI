---
name: API Contract Governance
description: Maintains strict API contracts, versioning discipline, and backward compatibility checks.
tags: api, contracts, versioning, schema, compatibility
complexity: 4
source: system-default
updated_at: 2026-03-12T01:43:55.915099+00:00
---

# API Contract Governance

Maintains strict API contracts, versioning discipline, and backward compatibility checks.

## Mission
- Execute this skill at depth level `4`.
- Optimize for correctness, reversibility, and measurable progress.

## Required Inputs
- Objective text
- Current repository state
- Constraints (security/runtime/performance)

## Workflow
1. Define and validate request/response envelopes before endpoint edits.
2. Guard compatibility with explicit additive-only default strategy.
3. Introduce clear deprecation markers and migration guidance when needed.
4. Add endpoint-level tests for status codes and shape integrity.

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