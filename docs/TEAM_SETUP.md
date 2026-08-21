# BebshaX — Team Setup

Get from `git clone` to green tests in ~5 minutes. Read [PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md) and [RULES.md](../RULES.md) first.

## Prerequisites

| Tool | Version | Required for |
|---|---|---|
| Python | 3.12+ | backend (now) |
| Git | any recent | everything |
| Docker Desktop | any recent | database (Phase 6+) |
| Node.js | 20+ | frontend (Phase 12+) |
| Ollama | 0.20+ | local fallback (Phase 4+, optional for backend work) |

## Setup

```powershell
git clone https://github.com/Tayebbb/BebshaX.git
cd BebshaX

python -m venv .venv
.venv\Scripts\pip install -e "apps/backend[dev]"

# verify
.venv\Scripts\python -m pytest apps/backend/tests -q

# run the API
.venv\Scripts\python -m uvicorn bebshax.main:app --port 8000
# → http://127.0.0.1:8000/api/health
```

macOS/Linux: replace `.venv\Scripts\` with `.venv/bin/`.

## Configuration

```powershell
Copy-Item .env.example .env   # then edit
```

- All BebshaX settings use the `BEBSHAX_*` prefix — see [.env.example](../.env.example).
- **Provider keys are optional.** The system runs keyless (Pollinations, OVHcloud, Kilo, LLM7). Add whatever legitimate free-tier keys *you personally* own to raise capacity — never share accounts, never create duplicates (RULES.md R4/R5).
- Free key signup pages (no card): Groq `console.groq.com/keys` · Google AI Studio `aistudio.google.com/apikey` · NVIDIA NIM `build.nvidia.com` · Mistral `console.mistral.ai/api-keys` · Cerebras · OpenRouter `openrouter.ai/keys` · Cohere `dashboard.cohere.com/api-keys` · GitHub Models (any PAT).

## Database (Phase 6+)

```powershell
docker compose up -d db   # pgvector/pgvector:pg16 on localhost:5433 (native PG16 keeps 5432)
```

## Everyday commands

| Do | Command |
|---|---|
| Run tests | `.venv\Scripts\python -m pytest apps/backend/tests -q` |
| Run API | `.venv\Scripts\python -m uvicorn bebshax.main:app --port 8000` |
| Keyless routing smoke test (real network) | `.venv\Scripts\python scripts/smoke_freellmpool.py` |
| Refresh dependency lock after changing pyproject | `.venv\Scripts\pip freeze --exclude-editable > apps/backend/requirements.lock` |

## Before you push

1. Tests green (R7).
2. No secrets in the diff (R4).
3. If you added a dependency: write the review (R8).
4. Phase work? Update the implementation log in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).
