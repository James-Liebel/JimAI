---
name: UX and Product Clarity
description: Simplifies UX, improves visual hierarchy, and removes user confusion.
tags: ux, ui, accessibility, copy, product
complexity: 3
source: system-default
updated_at: 2026-03-12T01:43:55.905159+00:00
---

# UX and Product Clarity

Simplifies UX, improves visual hierarchy, and removes user confusion.

## Mission
- Execute this skill at depth level `3`.
- Optimize for correctness, reversibility, and measurable progress.

## Required Inputs
- Objective text
- Current repository state
- Constraints (security/runtime/performance)

## Workflow
1. Reduce required user decisions and automate low-risk defaults.
2. Make editable inputs explicit and stateful actions obvious.
3. Improve spacing, labels, and status feedback for comprehension.
4. Ensure desktop/mobile usability with no broken interaction paths.

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