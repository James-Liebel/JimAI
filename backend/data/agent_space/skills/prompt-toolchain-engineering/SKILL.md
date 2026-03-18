---
name: Prompt and Toolchain Engineering
description: Builds high-signal prompts, tool policies, and deterministic fallback paths for agent execution.
tags: prompt, tools, llm, fallback, determinism
complexity: 5
source: system-default
updated_at: 2026-03-12T01:43:55.913290+00:00
---

# Prompt and Toolchain Engineering

Builds high-signal prompts, tool policies, and deterministic fallback paths for agent execution.

## Mission
- Execute this skill at depth level `5`.
- Optimize for correctness, reversibility, and measurable progress.

## Required Inputs
- Objective text
- Current repository state
- Constraints (security/runtime/performance)

## Workflow
1. Constrain prompt contracts with strict output schemas and failure behaviors.
2. Map which tools are mandatory, optional, or prohibited per objective stage.
3. Add retry policy with simplified prompts for recoverable failures.
4. Track action outcomes to continuously tighten prompt quality.

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