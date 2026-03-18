---
name: Agentic Parallel Orchestration
description: Designs complex multi-agent plans with controlled parallelism and robust handoffs.
tags: agents, parallel, orchestration, handoff, verification
complexity: 5
source: system-default
updated_at: 2026-03-12T01:43:55.912113+00:00
---

# Agentic Parallel Orchestration

Designs complex multi-agent plans with controlled parallelism and robust handoffs.

## Mission
- Execute this skill at depth level `5`.
- Optimize for correctness, reversibility, and measurable progress.

## Required Inputs
- Objective text
- Current repository state
- Constraints (security/runtime/performance)

## Workflow
1. Partition objective into independent workstreams with explicit dependency edges.
2. Define planner, implementers, reviewers, and verifier responsibilities.
3. Require structured inter-agent messages for assumptions, outputs, and blockers.
4. Enforce verification gates and fallback routing before completion.

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