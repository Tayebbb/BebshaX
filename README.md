# BebshaX

BebshaX is a synthetic-user / persona research system: it continuously generates realistic, evidence-grounded personas for a specific business or product and lets those personas participate in interviews and simulations — built on essentially zero API budget by aggregating **legitimate** free LLM capacity behind intelligent routing, failover, and context-aware model selection.

> Renamed from *SignalLens* on 2026-08-22. No other historical relationship — the project is greenfield.

**Team members start here:** [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) (single source of truth) → [RULES.md](RULES.md) (binding engineering rules) → [docs/TEAM_SETUP.md](docs/TEAM_SETUP.md) (machine setup).

## Repository layout

| Path | Purpose |
|---|---|
| `apps/backend/` | FastAPI backend (Python 3.12, async) — package `bebshax` |
| `apps/frontend/` | React + Vite single-page app (added in Phase 12) |
| `services` (inside backend) | `bebshax.llm` policy layer → adapters → freellmpool / Ollama |
| `data/raw` · `data/processed` · `data/metadata` | Datasets (reproducible via `scripts/`, not committed) |
| `scripts/` | Setup, dataset, and evaluation tooling |
| `docs/` | [AI_INFRASTRUCTURE_AUDIT.md](docs/AI_INFRASTRUCTURE_AUDIT.md) · [IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) |

## Quickstart (state: Phase 1 — foundation)

```powershell
# Backend
python -m venv .venv
.venv\Scripts\pip install -e "apps/backend[dev]"
.venv\Scripts\python -m pytest apps/backend/tests -q

# Run the API
.venv\Scripts\python -m uvicorn bebshax.main:app --port 8000
# → GET http://127.0.0.1:8000/api/health

# Database (pgvector; the native PG16 install lacks the extension, so Docker on port 5433)
docker compose up -d db   # used from Phase 6 onward
```

Configuration is environment-driven (`BEBSHAX_*` variables; see [.env.example](.env.example)). Provider API keys are **optional** — add whatever legitimate free-tier keys the team has; keyless providers work with none.
