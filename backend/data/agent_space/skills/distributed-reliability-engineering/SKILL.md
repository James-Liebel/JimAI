---
name: Distributed Reliability Engineering
description: Hardens long-running and multi-service flows against partial failure and degraded dependencies.
tags: reliability, distributed, retries, timeouts, resilience
complexity: 5
source: system-default
updated_at: 2026-03-12T01:43:55.914141+00:00
---

# Distributed Reliability Engineering

Hardens long-running and multi-service flows against partial failure and degraded dependencies.

## Mission
- Execute this skill at depth level `5`.
- Optimize for correctness, reversibility, and measurable progress.

## Required Inputs
- Objective text
- Current repository state
- Constraints (security/runtime/performance)

## Workflow
1. Identify failure domains and non-idempotent operations before changes.
2. Apply per-step timeout, retry budget, and circuit-breaker style guardrails.
3. Ensure service degradation paths still return useful partial outputs.
4. Publish failure telemetry and remediation actions with timestamps.

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