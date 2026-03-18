---
name: Research and Source Grounding
description: Runs broad source discovery and uses evidence before claims.
tags: research, web, sources, validation, facts
complexity: 4
source: system-default
updated_at: 2026-03-12T01:43:55.903157+00:00
---

# Research and Source Grounding

Runs broad source discovery and uses evidence before claims.

## Mission
- Execute this skill at depth level `4`.
- Optimize for correctness, reversibility, and measurable progress.

## Required Inputs
- Objective text
- Current repository state
- Constraints (security/runtime/performance)

## Workflow
1. Expand ambiguous queries into multiple high-signal variants.
2. Collect and deduplicate sources before synthesis.
3. Prefer primary sources and current data for unstable facts.
4. Report uncertainty explicitly when confidence is low.

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