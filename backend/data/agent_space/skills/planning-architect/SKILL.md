---
name: Planning Architect
description: Creates execution plans, milestones, and dependency-safe delivery strategy.
tags: planning, architecture, dependencies, milestones
complexity: 5
source: system-default
updated_at: 2026-03-12T01:43:55.898208+00:00
---

# Planning Architect

Creates execution plans, milestones, and dependency-safe delivery strategy.

## Mission
- Execute this skill at depth level `5`.
- Optimize for correctness, reversibility, and measurable progress.

## Required Inputs
- Objective text
- Current repository state
- Constraints (security/runtime/performance)

## Workflow
1. Map scope, constraints, and acceptance criteria before writing code.
2. Break work into parallel-safe tracks with explicit dependencies.
3. Define risk list and mitigation checks before execution starts.
4. Output deterministic plan + checkpoints + fallback path.

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