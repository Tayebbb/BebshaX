# BebshaX — Copilot Instructions

**The single agent contract for this repo is [AGENTS.md](../AGENTS.md).** Read it first, then [PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md) and [RULES.md](../RULES.md). This file only adds the verified command table.

## Commands (verified against this repo)

| Action | Command (Windows dev machine) |
| --- | --- |
| Install backend | `.venv\Scripts\pip install -e "apps/backend[dev]"` |
| Test (unit) | `.venv\Scripts\python -m pytest apps/backend/tests -q` |
| Test (integration, needs db) | `.venv\Scripts\python -m pytest apps/backend/tests -m integration -q` |
| Run API | `.venv\Scripts\python -m uvicorn bebshax.main:app --port 8000` |
| Database | `docker compose up -d db` then `cd apps/backend && ..\..\.venv\Scripts\python -m alembic upgrade head` |
| Datasets | `.venv\Scripts\python scripts/setup_datasets.py --profile minimal` |
| Frontend | `cd apps/frontend && npm ci && npm run build && npm test -- --run` |

CI runs Ubuntu (`python -m pytest apps/backend/tests -q`) — keep code and tests portable.
