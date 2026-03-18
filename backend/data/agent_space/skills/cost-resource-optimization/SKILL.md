---
name: Cost and Resource Optimization
description: Reduces compute/runtime cost with efficiency controls and budget-aware defaults.
tags: cost, resource, optimization, budget, efficiency
complexity: 3
source: system-default
updated_at: 2026-03-12T01:43:55.922881+00:00
---

# Cost and Resource Optimization

Reduces compute/runtime cost with efficiency controls and budget-aware defaults.

## Mission
- Execute this skill at depth level `3`.
- Optimize for correctness, reversibility, and measurable progress.

## Required Inputs
- Objective text
- Current repository state
- Constraints (security/runtime/performance)

## Workflow
1. Identify expensive operations and estimate impact of optimization options.
2. Apply caching, batching, and bounded timeouts where safe.
3. Set budget guardrails and fallback behavior for high-cost paths.
4. Track before/after cost or latency improvements with evidence.

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