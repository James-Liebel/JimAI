---
name: Design System Integrity
description: Enforces coherent visual language, spacing system, and component consistency.
tags: design-system, ui, consistency, accessibility, components
complexity: 3
source: system-default
updated_at: 2026-03-12T01:43:55.919609+00:00
---

# Design System Integrity

Enforces coherent visual language, spacing system, and component consistency.

## Mission
- Execute this skill at depth level `3`.
- Optimize for correctness, reversibility, and measurable progress.

## Required Inputs
- Objective text
- Current repository state
- Constraints (security/runtime/performance)

## Workflow
1. Consolidate repeated style patterns into reusable component classes.
2. Enforce spacing/typography tokens for predictable visual rhythm.
3. Eliminate ambiguous interactive states across forms and buttons.
4. Validate readability and contrast on all major surfaces.

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