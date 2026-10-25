# CivicPulse AI — Planning Documents

Read in this order. Each document builds on the previous one.

| # | Document | What it answers |
|---|----------|-----------------|
| 1 | [01-prd.md](01-prd.md) | What are we building, for whom, and how do we know it works? |
| 2 | [02-user-flows.md](02-user-flows.md) | How does each user move through the product, step by step? |
| 3 | [03-database-schema.md](03-database-schema.md) | What is the data model? (PostgreSQL + PostGIS + pgvector DDL) |
| 4 | [04-api-contracts.md](04-api-contracts.md) | What endpoints exist, who can call them, what do they return? |
| 5 | [05-architecture.md](05-architecture.md) | How are the services structured, and why? (diagrams + decision records) |
| 6 | [06-build-plan.md](06-build-plan.md) | In what order do we build it, and what does "done" mean per phase? |

## Rules for these docs

1. **Docs are contracts.** When you change a decision mid-build, update the doc in the same commit. A stale planning doc is worse than none.
2. **The ADRs in 05-architecture.md record *why*.** Six months from now (or in an interview) "why pgvector and not FAISS?" must have a written answer.
3. **Scope changes go through the PRD.** If a feature isn't in the PRD scope table, you don't build it this phase.

## Glossary

| Term | Meaning |
|------|---------|
| **Complaint** | One report from one citizen. Raw input. Never the unit of government work. |
| **Issue** | The deduplicated, real-world problem (one pothole). Many complaints attach to one issue. The unit of all triage, assignment, and analytics. |
| **Ward** | Smallest administrative area (polygon). Every issue belongs to exactly one ward. |
| **SLA** | Hours a category allows for resolution before the issue is flagged as breached/escalated. |
| **Triage** | Official reviews AI suggestions (category, duplicate-attachment, priority) and confirms or corrects them. Corrections become training data. |
| **Hotspot** | Spatial cluster of open issues; *emerging* hotspot = cluster whose recent rate significantly exceeds its baseline. |
| **AI pipeline** | The async job chain every new complaint passes through: embed → classify → CV → dedupe → score → notify. |
