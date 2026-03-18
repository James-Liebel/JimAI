---
name: Observability and Incident Ops
description: Improves diagnostics with metrics/logs/traces and incident-ready operating procedures.
tags: observability, metrics, logging, incident, monitoring
complexity: 4
source: system-default
updated_at: 2026-03-12T01:43:55.917423+00:00
---

# Observability and Incident Ops

Improves diagnostics with metrics/logs/traces and incident-ready operating procedures.

## Mission
- Execute this skill at depth level `4`.
- Optimize for correctness, reversibility, and measurable progress.

## Required Inputs
- Objective text
- Current repository state
- Constraints (security/runtime/performance)

## Workflow
1. Define service health indicators and failure thresholds by component.
2. Instrument critical paths with low-noise, high-signal telemetry.
3. Create incident triage playbook with first-response checklist.
4. Capture post-incident lessons as concrete engineering actions.

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