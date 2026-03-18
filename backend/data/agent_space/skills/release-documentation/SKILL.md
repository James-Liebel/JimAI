---
name: Release and Documentation
description: Keeps changelogs, runbooks, and capability docs synchronized.
tags: docs, release, changelog, runbook, handoff
complexity: 2
source: system-default
updated_at: 2026-03-12T01:43:55.911081+00:00
---

# Release and Documentation

Keeps changelogs, runbooks, and capability docs synchronized.

## Mission
- Execute this skill at depth level `2`.
- Optimize for correctness, reversibility, and measurable progress.

## Required Inputs
- Objective text
- Current repository state
- Constraints (security/runtime/performance)

## Workflow
1. Summarize user-visible behavior changes and migration notes.
2. Update capability docs with concrete paths and limits.
3. Capture unresolved risks and next operational steps.
4. Ensure rollback/undo instructions remain accurate.

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