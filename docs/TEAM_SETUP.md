# BebshaX — Team Setup

## Current Operations Contract (2026-09-10)

Use [SETUP.md](SETUP.md) for the current root-workspace install, production path,
explicit direct migrations, immutable model mount and recovery procedures.
The detailed original setup below is retained as historical evidence, not an
instruction to reinstall old dependencies, seed a database or start Ollama.

- No local or cloud Ollama live-inference path remains in ops launchers. CPU
	persona selection and labeled cached examples are not offline conversation.
- The existing root npm lock is authoritative. Use `npm run build`,
	`npm run test:frontend`, `npm run test:ops`, or sequential `npm test` from root.
	Do not use nested `npm install`, regenerate with `pip freeze`, or modify a
	shared environment while another agent is testing.
- `npm run dev`, `npm run dev:frontend` and `npm run dev:backend` are loopback-only.
	`npm start` runs the guarded single-worker production API, with no reload,
	database startup or migrations; a supervisor and HTTPS/static delivery are
	operator-owned prerequisites.
- `BEBSHAX_REMOTE_PROCESSING_POLICY` accepts the JSON contract in
	[SETUP.md](SETUP.md#remote-processing-is-denied-by-default). Default and example
	approvals are empty. Provider keys are not consent; private providers and
	OpenRouter upstreams require independent approval, never a copied example list.
- Stage a trusted compatible bundle, configure its approved metadata SHA256 and
	mount it read-only. Do not retrain, download weights or rewrite metadata on boot.
- Supply migration credentials by process-variable name, not command-line URL.
	`scripts/migrate_db.py` plans by default and requires exact target confirmation;
	apply and remote access are separate explicit choices. No production migration
	or recovery rehearsal was executed in this batch.

After the concurrent-test batch, clean-checkout installs are exactly:

```powershell
.venv/Scripts/python.exe scripts/ops/dependencies.py install
npm ci --workspaces --include-workspace-root
npm run check:npm-graph
npm run build
npm test
```

The current matching environment needs no install for these ops code changes.
[DEPENDENCY_REVIEWS.md](DEPENDENCY_REVIEWS.md) records verified versions and the
blocked skill-required Vite/Vitest upgrade. Production remains blocked pending
the external gates in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).

<details>
<summary>Historical setup evidence (superseded; not current release instructions)</summary>

Set up the application, offline tests, and local persona artifact. Download/training time is separate from environment setup. Read [PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md) and [RULES.md](../RULES.md) first.

## Prerequisites

| Tool           | Version    | Required for                                         |
| -------------- | ---------- | ---------------------------------------------------- |
| Python         | 3.12+      | backend (now)                                        |
| Git            | any recent | everything                                           |
| Docker Desktop | any recent | database (Phase 6+)                                  |
| Node.js        | 24 LTS     | frontend; CI + the `web` image use 24 (20+ builds)   |
| Ollama         | 0.20+      | local fallback (Phase 4+, optional for backend work) |

## Setup

```powershell
git clone https://github.com/Tayebbb/BebshaX.git
cd BebshaX

python -m venv .venv
.venv/Scripts/pip.exe install -c ml_persona/constraints.txt -e ml_persona -e "apps/backend[dev]"

# verify
.venv\Scripts\python -m pytest apps/backend/tests -q
.venv\Scripts\python -m pytest ml_persona/tests -q

# After configuring secrets and applying database migrations below, run the API
.venv\Scripts\python -m uvicorn bebshax.main:app --host 127.0.0.1 --port 8000
# → http://127.0.0.1:8000/api/health
```

Install both local Python packages even when no ML artifact is available. The
CPU-only reference model has been trained/evaluated locally, but its ~32.54 MiB
bundle is Git-ignored and not supplied by a fresh checkout. Serving uses
`BEBSHAX_ML_PERSONA_ARTIFACT_DIR`, default `data/processed/ml_persona/model` with
unchanged data roots. The constraints above pin the exact NumPy/SciPy/scikit-learn
versions required by that bundle and used by the backend image. The base setup
helper/CI installs are unconstrained; apply the pins or train a compatible bundle.
Chat/interview LLM routing is unchanged.

### Prepare the persona artifact

Run from the repository root for a fresh artifact:

```powershell
.venv/Scripts/python.exe -m bebshax_persona_ml download
.venv/Scripts/python.exe -m bebshax_persona_ml prepare
.venv/Scripts/python.exe -m bebshax_persona_ml validate
.venv/Scripts/python.exe -m bebshax_persona_ml train --config ml_persona/configs/training.json
.venv/Scripts/python.exe -m bebshax_persona_ml evaluate
.venv/Scripts/python.exe -m bebshax_persona_ml generate --input ml_persona/examples/business.json --num-personas 5
.venv/Scripts/python.exe -m bebshax_persona_ml smoke --backend --input ml_persona/examples/business.json
```

Only download needs network; no API key, API/DB server, LLM, or GPU is needed.
`download` delegates to the independent `ml_persona` profile, not included in
`full`. Do not overwrite existing outputs or retune on the inspected test set:
on the trained checkout, use generation/smoke directly. There is no console
entry point; use `python -m bebshax_persona_ml`. `--backend` adds schema/conversion
checks, not live API/DB validation. See [ML README](../ml_persona/README.md).

The model selects synthetic USA source profiles, not new customer identities.
Role/location are hints, explicit ages are hard bounds in 18–95, and missing
income/OCEAN stays unknown. It underperforms lexical TF-IDF on held-out retrieval.
No LLM fallback is attempted: missing/incompatible models return 503;
unsupported/exhausted contexts return 422. Restart after replacing a trusted
validated bundle. See [SETUP.md](SETUP.md#persona-ml-artifact) for path resolution.

### Verified repo commands (Last verified: 2026-09-02)

| Workflow       | Command                                                                         |
| -------------- | ------------------------------------------------------------------------------- |
| Full stack     | `node scripts/dev.js`                                                           |
| Backend only   | `.venv\Scripts\python -m uvicorn bebshax.main:app --host 127.0.0.1 --port 8000` |
| Frontend only  | `cd apps/frontend; npm run dev`                                                 |
| DB bootstrap   | `docker compose up -d --wait db`                                                |
| Migrations     | `.venv\Scripts\python -m alembic -c apps/backend/alembic.ini upgrade head`      |
| Frontend test  | `cd apps/frontend; npm test -- --run`                                           |
| Frontend build | `cd apps/frontend; npm run build`                                               |

macOS/Linux: replace `.venv\Scripts\` with `.venv/bin/`.

## Configuration

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

- All BebshaX settings use the `BEBSHAX_*` prefix — see [.env.example](../.env.example).
- Preserve existing valid secrets and database settings. A new API environment needs a unique `BEBSHAX_JWT_SECRET` of at least 32 characters; use the [secret setup](SETUP.md#3-secrets). JWT expiry defaults to one day.
- **Provider keys are optional.** The system runs keyless (Pollinations, OVHcloud, Kilo, LLM7). Add whatever legitimate free-tier keys _you personally_ own to raise capacity — never share accounts, never create duplicates (RULES.md R4/R5).
- Free key signup pages (no card): Groq `console.groq.com/keys` · Google AI Studio `aistudio.google.com/apikey` · NVIDIA NIM `build.nvidia.com` · Mistral `console.mistral.ai/api-keys` · Cerebras · OpenRouter `openrouter.ai/keys` · Cohere `dashboard.cohere.com/api-keys` · GitHub Models (any PAT).

## Database (Phase 6+)

```powershell
docker compose up -d db   # pgvector/pgvector:pg16 on localhost:5433 (native PG16 keeps 5432)

# After database is running (Phase 6 completed):
.venv\Scripts\python -m alembic -c apps/backend/alembic.ini upgrade head   # Apply all schema migrations
```

## Frontend (Phase 12+)

```powershell
cd apps/frontend
npm install
npm run dev        # Runs dev server on http://localhost:5173
npm test           # Runs Vitest component & API tests
npm run build      # Verifies TypeScript & builds production bundle
```

## Everyday commands

| Do                                               | Command                                                                                                 |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| Run backend tests                                | `.venv\Scripts\python -m pytest apps/backend/tests -q`                                                  |
| Run frontend tests                               | `cd apps/frontend; npm test`                                                                            |
| Run API                                          | `.venv\Scripts\python -m uvicorn bebshax.main:app --port 8000`                                          |
| Run Frontend Dev Server                          | `cd apps/frontend; npm run dev`                                                                         |
| Build Frontend                                   | `cd apps/frontend; npm run build`                                                                       |
| Keyless routing smoke test (real network)        | `.venv\Scripts\python scripts/smoke_freellmpool.py`                                                     |
| Refresh dependency lock after changing pyproject | `.venv\Scripts\pip freeze --exclude-editable \| Out-File -Encoding utf8 apps/backend/requirements.lock` |
| Download datasets (minimal profile)              | `.venv\Scripts\python scripts/setup_datasets.py --profile minimal`                                      |
| Download datasets (development profile)          | `.venv\Scripts\python scripts/setup_datasets.py --profile development`                                  |
| Download approved synthetic training profile | `.venv/Scripts/python.exe scripts/setup_datasets.py --profile ml_persona` |
| ML local/backend-contract smoke (trained checkout) | `.venv/Scripts/python.exe -m bebshax_persona_ml smoke --backend --input ml_persona/examples/business.json` |
| Verify dataset revisions & files (offline check) | `.venv\Scripts\python scripts/setup_datasets.py --verify-only`                                          |

## Before you push

1. Tests green (R7).
2. No secrets in the diff (R4).
3. If you added a dependency: write the review (R8).
4. Keep affected docs with the change. ML work is maintenance: add a maintenance entry to [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), not phase 16, and preserve the original phase dates.
5. Record actual gates after integrating remote changes; historical test counts and smoke observations are not a new CI/push result. Do not commit raw data, splits, model bundles, or secrets.

</details>
