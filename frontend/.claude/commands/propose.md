You are running a 9-stage Change Pipeline for the following proposed change:

> $ARGUMENTS

Work through each stage in order. For every stage, print a header like:
  ── Stage N: [Name] [emoji] ──
then produce that stage's output before moving to the next.

Use your tools (Read, Grep, Glob, Bash) throughout to ground every decision in the actual codebase — don't reason from memory alone.

---

**Stage 1 — Analyst 🔍**
Scope the change precisely:
- What exactly is changing and why
- Which users/systems are affected
- Unknowns that must be resolved before implementation
- One-paragraph summary for the stages below

**Stage 2 — Researcher 📚**
Search the codebase for relevant context:
- Existing files, components, or patterns this change touches
- Conventions already in use that must be followed
- Known gotchas or constraints for this type of change
- Any security, performance, or compatibility concerns to flag early

**Stage 3 — Architect 🏛️**
Design the technical approach:
- Which files/modules need to change (with paths)
- Any API contract or data flow changes
- Trade-offs between approaches with a clear recommendation
- New abstractions or patterns needed, if any

**Stage 4 — Planner 📋**
Produce a numbered implementation plan:
- Each step must be atomic and independently verifiable
- Include migration or rollback steps if applicable
- Flag any step that needs human confirmation before proceeding
- Estimate relative effort per step: small / medium / large

**Stage 5 — Coder 💻**
Write the actual code changes following the plan:
- Show complete changed sections (not just diffs) for every file
- Write clean, idiomatic code — no unnecessary comments
- Note inline if anything in the plan is unclear or risky

**Stage 6 — Security 🔒**
Review the code produced in Stage 5:
- Check for injection, improper auth/authz, secret exposure
- Identify unvalidated inputs at system boundaries
- Flag unsafe dependencies or patterns
- Rate each finding: Critical / High / Medium / Low

**Stage 7 — Tester 🧪**
Write tests and identify edge cases:
- Unit test cases (inputs → expected outputs)
- Integration test scenarios for changed flows
- Edge cases and failure modes to cover
- Regression risks introduced by this change

**Stage 8 — Reviewer 👁️**
Final code quality review:
- Readability and naming
- Logical correctness — does it actually implement the plan?
- Performance concerns
- Anything the Integrator must fix before shipping

**Stage 9 — Integrator 🎯**
Produce the definitive final output:
- Apply all reviewer and security fixes to the code
- Show the complete, ready-to-apply implementation
- Write a short summary: what changed, why, what was caught en route
- List any items requiring human sign-off before deploying

---

After Stage 9, print a final section:
  ══ PIPELINE COMPLETE ══
  [one-paragraph executive summary of the full pipeline output]
  [bulleted list of any human sign-off items, or "None" if clean]
