---
name: Performance Optimizer
description: Improves latency/throughput, compacts heavy flows, and removes bottlenecks.
tags: performance, latency, throughput, optimization, async
complexity: 3
source: system-default
updated_at: 2026-03-12T01:43:55.909882+00:00
---

# Performance Optimizer

Improves latency/throughput, compacts heavy flows, and removes bottlenecks.

## Mission
- Execute this skill at depth level `3`.
- Optimize for correctness, reversibility, and measurable progress.

## Required Inputs
- Objective text
- Current repository state
- Constraints (security/runtime/performance)

## Workflow
1. Measure hot paths and avoid sequential I/O where parallel is safe.
2. Use bounded timeouts and fallbacks for external dependencies.
3. Reduce payload size and unnecessary render/update churn.
4. Document measurable before/after impact.

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