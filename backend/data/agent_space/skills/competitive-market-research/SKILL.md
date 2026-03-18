---
name: Competitive and Market Research
description: Runs structured competitor and market scans with evidence-backed recommendations.
tags: market, competitive, research, pricing, positioning
complexity: 4
source: system-default
updated_at: 2026-03-12T01:43:55.920565+00:00
---

# Competitive and Market Research

Runs structured competitor and market scans with evidence-backed recommendations.

## Mission
- Execute this skill at depth level `4`.
- Optimize for correctness, reversibility, and measurable progress.

## Required Inputs
- Objective text
- Current repository state
- Constraints (security/runtime/performance)

## Workflow
1. Frame hypotheses and define competitor comparison criteria first.
2. Gather sources from multiple domains and normalize key facts.
3. Separate verified evidence from inference in findings.
4. Translate findings into prioritized product/monetization actions.

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