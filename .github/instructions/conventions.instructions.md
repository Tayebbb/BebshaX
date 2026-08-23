---
description: "Project-specific conventions that differ from common defaults."
applyTo: "**"
---

# Project Conventions

- Every LLM call goes through `LLMService.complete(LLMRequest)` with an explicit `TaskType` — no direct provider calls (RULES.md R1/R3).
- Provider SDK imports only inside `apps/backend/bebshax/llm/adapters/` (test-enforced).
- Pools, task→pool mappings, and consistency rules are **data tables**, not code branches — extend the table + add a test.
- New DB tables go in the owning feature package (`bebshax/<feature>/orm.py`) on the shared `Base`; hand-written alembic migration; register the ORM import in `alembic/env.py`.
- Test helpers are shared via conftest **fixtures**, never `from tests.… import` (tests/ is not a package); test module basenames must be unique across test dirs.
- Docs update in the same commit as code (R12); implementation log is append-only, newest entry on top.
- Patterns to avoid: silent truncation of persona context; treating low answer quality as an infra failure; adding failure kinds without policy+tests; hard-coded provider lists.
