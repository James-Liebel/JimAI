# JimAI-1 — Markdown File Tree

Excludes `node_modules` and duplicate skill copies under `data/` (mirrors of `backend/data/`).

```
JimAI-1/
│
├── README.md                        Main project intro and setup guide
├── STRUCTURE.md                     App layer overview (architecture summary)
├── AGENTS.md                        Agent system documentation
├── CHANGELOG.md                     Version history
│
├── docs/
│   ├── architecture.md              Deeper architecture notes
│   ├── AUDITOR_ISSUES.md            Known issues flagged by auditor
│   └── SEARCH_AUDIT_REPORT.md       Search feature audit findings
│
├── skills/
│   ├── README.md                    Skills system overview
│   └── shared/
│       ├── general-reasoning.md     Shared reasoning skill definition
│       └── output-formatting.md     Shared output formatting skill
│
├── backend/
│   └── data/agent_space/skills/     Agent skill definitions (SKILL.md per skill)
│       ├── agentic-parallel-orchestration/
│       ├── api-contract-governance/
│       ├── competitive-market-research/
│       ├── cost-resource-optimization/
│       ├── data-schema-evolution/
│       ├── design-system-integrity/
│       ├── distributed-reliability-engineering/
│       ├── fullstack-implementation/
│       ├── mobile-interaction-performance/
│       ├── observability-incident-ops/
│       ├── performance-optimizer/
│       ├── planning-architect/
│       ├── product-analytics-experimentation/
│       ├── prompt-toolchain-engineering/
│       ├── release-documentation/
│       ├── research-source-grounding/
│       ├── security-guardrails/
│       ├── testing-reliability/
│       ├── ux-product-clarity/
│       └── zero-downtime-change-management/
│
└── [reports — generated artifacts, not source docs]
    ├── COMPLETION_REPORT.md
    ├── ORIENTATION_REPORT.md
    ├── SEARCH_FIX_VALIDATION.md
    ├── SEARCH_TEST_RESULTS.md        (also duplicated at backend/)
    └── SECURITY_REVIEW.md
```
