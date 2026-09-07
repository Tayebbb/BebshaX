# Fresh-Machine Setup

Everything needed to run BebshaX from a clean checkout. One-shot: `python scripts/setup.py` automates steps 2–6 below. Windows commands shown; macOS/Linux use `.venv/bin/` instead of `.venv\Scripts\`.

## 0. Prerequisites

| Tool           | Version    | Notes                                                                              |
| -------------- | ---------- | ---------------------------------------------------------------------------------- |
| Python         | 3.12+      | `python --version`                                                                 |
| Node.js        | 24 LTS     | `node --version` — CI and the `web` image use Node 24; 20+ still builds locally    |
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

| Flow             | Command                                                                         |
| ---------------- | ------------------------------------------------------------------------------- |
| Full stack       | `node scripts/dev.js`                                                           |
| Backend only     | `.venv\Scripts\python -m uvicorn bebshax.main:app --host 127.0.0.1 --port 8000` |
| Frontend only    | `cd apps/frontend; npm run dev`                                                 |
| DB on Docker     | `docker compose up -d --wait db`                                                |
| Apply migrations | `cd apps/backend; ..\..\.venv\Scripts\python -m alembic upgrade head`           |

The repo-level launcher in [../scripts/dev.js](../scripts/dev.js) is the reference path for daily development; it automatically starts Docker Postgres when available and prints the backend/frontend URLs without exposing credentials.

## 8. Optional: demo mode & offline drill

Set `BEBSHAX_DEMO_MODE=true` in `.env` to seed cached, clearly-labeled demo entities on an empty database. The full walkthrough and the network-unplugged drill live in [DEMO.md](DEMO.md).

## Deployment stories

Three distinct paths exist; the root-level files that confuse newcomers belong to the second one.

| Path                                        | What runs where                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | Files                                                                                                          |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| **Daily dev**                               | `node scripts/dev.js`: Docker `db` (pgvector, :5433) + uvicorn `--reload` (:8000) + Vite (:5173). Vite reads the repo-root `.env`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | `docker-compose.yml` (`db` only), `scripts/dev.js`                                                             |
| **Self-hosted / offline venue**             | `docker compose --profile full up --build -d`: `db` → `app` (backend image; runs `alembic upgrade head` then uvicorn; healthcheck on `/api/health`) → `web` (nginx serving the built SPA on :8080, proxying `/api`, security headers + CSP). `app` and `web` restart `unless-stopped`; `web` waits for `app` to be healthy. `./data/processed` and `./data/metadata` are bind-mounted read-only into `app` because `.dockerignore` excludes `data/` from the image — run `scripts/setup_datasets.py --profile minimal` on the host first or the EvidenceStore is empty. Host Ollama is reached via `host.docker.internal`. | `docker-compose.yml` (`full` profile), `apps/backend/Dockerfile`, `deploy/web.Dockerfile`, `deploy/nginx.conf` |
| **Cloud (frontend on Vercel + hosted API)** | Vercel builds `apps/frontend` (`npm run build` from the root `package.json`, output `apps/frontend/dist`, SPA rewrite) and the SPA calls a separately hosted API via `VITE_API_BASE`. The database is a pgvector-enabled cloud Postgres (e.g. Neon); the API host must set `BEBSHAX_CORS_ORIGINS` to the Vercel origin. `neon.ts` is the Neon CLI project config placeholder (`@neon/config`, empty `defineConfig({})`) — it configures nothing yet and is safe to ignore for the other two paths.                                                                                                                         | `vercel.json`, root `package.json` (workspace + build script), `neon.ts`, `apps/frontend/vercel.json`          |

Base images are pinned to minor tags (`python:3.12-slim`, `node:24.11-alpine`, `nginx:1.28-alpine`); digest pins were deliberately not added because the venue build box is offline — the recipe is in `deploy/web.Dockerfile`. Validate both compose graphs with `docker compose config --quiet` and `docker compose --profile full config --quiet` (CI does).

## Dependency review (RULES.md R8)

Routing-layer dependencies are reviewed in [ROUTING.md](ROUTING.md); platform ones live here.

### httpx ≥0.27 — promoted to runtime dependency (2026-09-06)

- **Why:** imported directly by `llm/adapters/ollama_adapter.py`, `llm/adapters/embeddings.py`, `llm/adapters/openrouter_adapter.py`, `datasets/discovery/world_bank_adapter.py` and the research fetchers, yet it was only declared in the `[dev]` extra and reached production installs transitively through freellmpool. A freellmpool release dropping/renaming it would have broken the API at import time.
- **Provides:** the async HTTP client for every provider/HTTP call outside freellmpool. **Replaces:** nothing new — already in use. **License:** BSD-3-Clause. **Activity:** 0.28.1 installed; actively maintained (encode). **Necessary:** yes — an undeclared direct import is a latent outage.

### python-dotenv ≥1.0 — promoted to runtime dependency (2026-09-06)

- **Why:** `bebshax/config.py` calls `dotenv.load_dotenv` at import; it arrived only transitively via pydantic-settings, whose extras could change.
- **Provides:** repo-root `.env` loading before `Settings` resolves. **License:** BSD-3-Clause. **Activity:** 1.2.3 installed; maintained. **Necessary:** yes for the same reason as httpx.

### pip-audit ≥2.7 — dev extra + advisory CI step (2026-09-06)

- **Why:** no vulnerability scan existed for the resolved Python environment (gitleaks covers secrets, not CVEs).
- **Provides:** PyPI advisory-database lookups for every installed distribution. **Replaces:** nothing. **License:** Apache-2.0 (PyPA). **Activity:** 2.10.1 installed; maintained by PyPA. **Necessary:** dev/CI only — never installed in the runtime image.
- **Baseline (2026-09-06, this venv):** `No known vulnerabilities found`; the editable `bebshax` package is skipped (not on PyPI — expected). The CI step is `continue-on-error: true` until it has passed once on Ubuntu's fresh resolution; then it becomes blocking (comment in `.github/workflows/ci.yml`).

## Environment variables

Names only — values live in `.env` (gitignored); [.env.example](../.env.example) documents every `Settings` field (a test enforces parity). Core: `BEBSHAX_APP_NAME`, `BEBSHAX_ENVIRONMENT`, `BEBSHAX_API_HOST`, `BEBSHAX_API_PORT`, `BEBSHAX_DEMO_MODE`, `BEBSHAX_LOG_LEVEL`, `BEBSHAX_CORS_ORIGINS`, `BEBSHAX_CORS_ORIGIN_REGEX` (default: localhost/127.0.0.1 on any port — deployed origins go in `BEBSHAX_CORS_ORIGINS`), `BEBSHAX_DATA_DIR` / `_UPLOAD_DIR` / `_PROCESSED_DIR`, `BEBSHAX_METADATA_DIR` (quality-gate reports for `/api/evaluation/metrics`; CWD-relative `data/metadata` by default), `BEBSHAX_DATABASE_URL`, `BEBSHAX_DB_POOL_SIZE` / `_MAX_OVERFLOW`, `BEBSHAX_JWT_SECRET`, `BEBSHAX_JWT_SECRET_PREVIOUS`, `BEBSHAX_JWT_EXPIRE_DAYS` (default 1), `BEBSHAX_JWT_ISSUER` / `_AUDIENCE` / `_ALGORITHM`, `BEBSHAX_NEON_AUTH_URL`, `BEBSHAX_REQUIRE_EMAIL_VERIFICATION`, `BEBSHAX_RATE_LIMIT_STORAGE_URI`, `BEBSHAX_RATE_LIMIT_TRUST_FORWARDED_FOR`, `BEBSHAX_EMBEDDING_BACKEND` / `_MODEL`, `BEBSHAX_RESEND_API_KEY`, `BEBSHAX_EMAIL_FROM_ADDRESS`, `BEBSHAX_FRONTEND_BASE_URL`, `BEBSHAX_SMTP_*`, `BEBSHAX_STRIPE_*`, `OLLAMA_API_BASE`. OpenRouter: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` (default model for the health check / `OpenRouterService` when no `MODEL_PERSONA|REASONING|EXTRACTION|CRITIC|BROWSER` override is set), `BEBSHAX_OPENROUTER_MODELS` (free-tier list override). Optional provider keys (each unlocks routes): `GROQ_API_KEY`, `GEMINI_API_KEY`, `NVIDIA_API_KEY`, `MISTRAL_API_KEY`, `CEREBRAS_API_KEY`, `COHERE_API_KEY`, `GITHUB_TOKEN`, `HF_TOKEN`, `CLOUDFLARE_API_TOKEN` + `_ACCOUNT_ID`. `FREELLMPOOL_CONFIG` is set automatically to the repo's `providers.toml`. Frontend build-time (baked in by Vite from the repo-root `.env`): `VITE_API_BASE`, `VITE_MOCK`, `VITE_NEON_AUTH_URL`. Not read by anything: `NEON_AUTH_BASE_URL`, `VITE_NEON_AUTH_JWKS_URL` (legacy — delete from your `.env`).

## Troubleshooting

- **Startup exits with a migration message** → run the alembic command from step 4; this is the drift guard doing its job (it only runs for local dev databases with demo mode off — the compose `full` profile migrates itself at start instead).
- **`node scripts/dev.js` prints a red FATAL box and stops** → the backend exited non-zero (config `FATAL`, migration drift, port 8000 busy); the launcher now stops Vite too instead of serving a UI with no API. Read the `[Backend]` lines above the box.
- **`vector` type errors** → your Postgres lacks pgvector; use the compose service (port 5433) or a pgvector-enabled cloud DB.
- **Backend edits kill `node scripts/dev.js`** → uvicorn's reloader watches the repo root; finish backend edits, then restart the launcher.
- **"local tier DOWN" warning at startup** → Ollama isn't running; only the offline drill and local pool need it (`ollama serve`).
