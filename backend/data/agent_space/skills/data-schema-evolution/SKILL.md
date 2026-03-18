---
name: Data Schema Evolution
description: Evolves data models safely with migration-aware patterns and rollback options.
tags: data, schema, migration, rollback, storage
complexity: 4
source: system-default
updated_at: 2026-03-12T01:43:55.916107+00:00
---

# Data Schema Evolution

Evolves data models safely with migration-aware patterns and rollback options.

## Mission
- Execute this skill at depth level `4`.
- Optimize for correctness, reversibility, and measurable progress.

## Required Inputs
- Objective text
- Current repository state
- Constraints (security/runtime/performance)

## Workflow
1. Document current and target schema with compatibility constraints.
2. Use two-step migrations when destructive operations are possible.
3. Add migration validation checks and backfill observability.
4. Keep rollback path tested for each schema transition.

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