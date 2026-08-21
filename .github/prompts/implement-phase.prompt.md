---
description: "Implement a BebshaX phase end-to-end following the Phase Execution Protocol"
---

Execute the **Phase Execution Protocol** defined in [AGENTS.md](../../AGENTS.md) for the phase the user names in this request (e.g. "4"). If no phase number is given, use the first ⬜ phase in the PROJECT_CONTEXT.md roadmap.

Steps you must not skip:
1. Read PROJECT_CONTEXT.md, RULES.md, the `## Phase N` spec in docs/PHASES.md, and docs/TEAM_ASSIGNMENTS.md.
2. Gate: prerequisites ✅ and `.venv\Scripts\python -m pytest apps/backend/tests -q` green — otherwise stop and report the blocker.
3. Implement only within the spec's allowed paths, with tests (R7) and dependency reviews (R8).
4. Run every exit-criteria verification command in the spec.
5. Update docs in the same commit: implementation-log entry, status flips in PROJECT_CONTEXT.md + docs/PHASES.md, plus the spec's listed docs.
6. Commit `Phase N: <summary>`, push to origin main, and report deliverables, test count, deviations, and the next phase.
