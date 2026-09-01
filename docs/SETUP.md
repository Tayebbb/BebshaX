# Fresh-Machine Setup

Everything needed to run BebshaX from a clean checkout. One-shot: `python scripts/setup.py` automates steps 2–6 below. Windows commands shown; macOS/Linux use `.venv/bin/` instead of `.venv\Scripts\`.

## 0. Prerequisites

| Tool           | Version    | Notes                                                                              |
| -------------- | ---------- | ---------------------------------------------------------------------------------- |
| Python         | 3.12+      | `python --version`                                                                 |
| Node.js        | 20+        | `node --version`                                                                   |
| Docker Desktop | any recent | only needed for the local Postgres; a cloud Postgres URL works instead             |
| Ollama         | optional   | required only for the offline drill / local model tier (`ollama pull llama3.2:3b`) |

**Zero API keys is a supported configuration** — freellmpool starts on keyless providers. Keys added to `.env` unlock more routes.

## 1. Clone

```bash
git clone https://github.com/Tayebbb/BebshaX.git
cd BebshaX
```

## 2. Python environment

```powershell
python -m venv .venv
.venv\Scripts\pip install -e "apps/backend[dev]"
```

## 3. Secrets

```powershell
copy .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the generated value as `BEBSHAX_JWT_SECRET` in `.env` (mandatory, ≥32 chars; the burned example value is rejected at startup). Never commit `.env` (R4).

## 4. Database

Local (Docker, pgvector on port **5433** — native PG16 installs usually own 5432 and lack pgvector):

```powershell
docker compose up -d db
cd apps/backend
..\..\.venv\Scripts\python -m alembic upgrade head
cd ..\..
```

Cloud alternative: set `BEBSHAX_DATABASE_URL` in `.env` to a pgvector-enabled Postgres (e.g. Neon) and run the same alembic command.

## 5. Datasets (grounding evidence)

```powershell
.venv\Scripts\python scripts/setup_datasets.py --profile minimal
```

Profiles nest: `minimal ⊂ development ⊂ evaluation ⊂ full`. Idempotent — re-runs are no-ops; `--verify-only` checks checksums. Licenses per dataset in [../data/DATASETS.md](../data/DATASETS.md).

## 6. Verify

```powershell
.venv\Scripts\python -m pytest apps/backend/tests -q
```

Expect all green (integration tests needing a live DB run with `-m integration`).

## 7. Run

Current verified launch path: use the repo root launcher so the backend and frontend start together with the expected ports.

```powershell
node scripts/dev.js
# API → http://127.0.0.1:8000/api/health
# UI  → http://localhost:5173
```

Or individually:

```powershell
.venv\Scripts\python -m uvicorn bebshax.main:app --host 127.0.0.1 --port 8000   # API → http://localhost:8000/api/health
cd apps/frontend; npm install; npm run dev                                        # UI  → http://localhost:5173
```

Frontend checks: `npm run build` (type-checks via tsc), `npm test -- --run`, `npm run theme:check` (theme-token drift gate).

### Verified startup matrix (Last verified: 2026-09-02)

| Flow | Command |
| --- | --- |
| Full stack | `node scripts/dev.js` |
| Backend only | `.venv\Scripts\python -m uvicorn bebshax.main:app --host 127.0.0.1 --port 8000` |
| Frontend only | `cd apps/frontend; npm run dev` |
| DB on Docker | `docker compose up -d --wait db` |
| Apply migrations | `cd apps/backend; ..\.venv\Scripts\python -m alembic upgrade head` |

The repo-level launcher in [../scripts/dev.js](../scripts/dev.js) is the reference path for daily development; it automatically starts Docker Postgres when available and prints the backend/frontend URLs without exposing credentials.

## 8. Optional: demo mode & offline drill

Set `BEBSHAX_DEMO_MODE=true` in `.env` to seed cached, clearly-labeled demo entities on an empty database. The full walkthrough and the network-unplugged drill live in [DEMO.md](DEMO.md).

## Environment variables

Names only — values live in `.env` (gitignored). Core: `BEBSHAX_ENVIRONMENT`, `BEBSHAX_API_HOST`, `BEBSHAX_API_PORT`, `BEBSHAX_DEMO_MODE`, `BEBSHAX_CORS_ORIGINS`, `BEBSHAX_DATABASE_URL`, `BEBSHAX_JWT_SECRET`, `BEBSHAX_JWT_SECRET_PREVIOUS`, `BEBSHAX_JWT_EXPIRE_DAYS`, `BEBSHAX_REQUIRE_EMAIL_VERIFICATION`, `BEBSHAX_EMBEDDING_BACKEND` / `_MODEL`, `BEBSHAX_RESEND_API_KEY`, `BEBSHAX_EMAIL_FROM_ADDRESS`, `BEBSHAX_FRONTEND_BASE_URL`, `OLLAMA_API_BASE`. Optional provider keys (each unlocks routes): `GROQ_API_KEY`, `GEMINI_API_KEY`, `NVIDIA_API_KEY`, `OPENROUTER_API_KEY`, `MISTRAL_API_KEY`, `CEREBRAS_API_KEY`, `COHERE_API_KEY`, `GITHUB_TOKEN`, `HF_TOKEN`, `CLOUDFLARE_API_TOKEN` + `_ACCOUNT_ID`. `FREELLMPOOL_CONFIG` is set automatically to the repo's `providers.toml`.

## Troubleshooting

- **Startup exits with a migration message** → run the alembic command from step 4; this is the drift guard doing its job.
- **`vector` type errors** → your Postgres lacks pgvector; use the compose service (port 5433) or a pgvector-enabled cloud DB.
- **Backend edits kill `node scripts/dev.js`** → uvicorn's reloader watches the repo root; finish backend edits, then restart the launcher.
- **"local tier DOWN" warning at startup** → Ollama isn't running; only the offline drill and local pool need it (`ollama serve`).
