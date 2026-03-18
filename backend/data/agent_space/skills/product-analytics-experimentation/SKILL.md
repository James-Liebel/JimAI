---
name: Product Analytics and Experimentation
description: Establishes event instrumentation, KPI definitions, and experiment execution rigor.
tags: analytics, kpi, events, experimentation, growth
complexity: 4
source: system-default
updated_at: 2026-03-12T01:43:55.921872+00:00
---

# Product Analytics and Experimentation

Establishes event instrumentation, KPI definitions, and experiment execution rigor.

## Mission
- Execute this skill at depth level `4`.
- Optimize for correctness, reversibility, and measurable progress.

## Required Inputs
- Objective text
- Current repository state
- Constraints (security/runtime/performance)

## Workflow
1. Define north-star metric and supporting diagnostic metrics.
2. Map required events and data quality checks before launch.
3. Specify experiment design, duration, and decision thresholds.
4. Produce concise result summary with recommended next iteration.

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