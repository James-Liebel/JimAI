---
name: Mobile and Interaction Performance
description: Optimizes mobile UI behavior, touch interactions, and render performance under constrained devices.
tags: mobile, touch, responsive, performance, ux
complexity: 4
source: system-default
updated_at: 2026-03-12T01:43:55.918374+00:00
---

# Mobile and Interaction Performance

Optimizes mobile UI behavior, touch interactions, and render performance under constrained devices.

## Mission
- Execute this skill at depth level `4`.
- Optimize for correctness, reversibility, and measurable progress.

## Required Inputs
- Objective text
- Current repository state
- Constraints (security/runtime/performance)

## Workflow
1. Audit viewport layout and interaction affordances for small screens.
2. Reduce repaint/reflow and avoid long synchronous UI tasks.
3. Validate form focus, scrolling, and keyboard behavior on mobile.
4. Keep text contrast and tappable targets consistently accessible.

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