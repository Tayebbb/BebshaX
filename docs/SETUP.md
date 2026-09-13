# Fresh-Machine Setup

## Current Release Foundations (2026-09-10)

The approved target is remote-only conversation: Freellmpool primary and an
independent OpenRouter secondary, subject to processing policy and quota.
CPU persona selection and labeled cached examples are separate capabilities.
There is **no offline live-inference guarantee** and no production sign-off.
[PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) records current blockers.
Historical setup instructions are archived at the end; do not execute their
open-range installs, local preflight, automatic migrations or demo defaults.

### Toolchain And Installation

- Python 3.12; image/CI patch 3.12.14, existing Windows check interpreter 3.12.9.
- Frozen artifact runtime: NumPy 2.5.2, SciPy 1.18.1, scikit-learn 1.9.0.
	Do not upgrade, retrain, replace weights or edit metadata to make a model load.
- Node 24.20.0 with bundled npm 11.19.0. The roadmap's 24.21.0 Docker tag was
	absent; the selected published version is pinned by verified digest.
- Docker/Compose and PG16 clients are operator-provisioned prerequisites, not
	 automatically installed. [DEPENDENCY_REVIEW.md](DEPENDENCY_REVIEW.md) records R8.

From the root, using an operator-provisioned Python 3.12 (Linux uses `.venv/bin/python`):

```powershell
python -m venv .venv
.venv/Scripts/python.exe scripts/ops/dependencies.py install
node scripts/ops/npm-graph.mjs
npm ci --workspaces --include-workspace-root
npm run build
npm test
```

The Python installer consumes [requirements.lock](../apps/backend/requirements.lock)
with hash verification and binary-only distributions, then installs both local
packages with `--no-deps --no-build-isolation` and runs `pip check`.
[requirements.txt](../apps/backend/requirements.txt) points only to that full lock.
The full closure includes ML/dev/audit/build tools; the runtime subset in
[deploy/python/runtime.lock](../deploy/python/runtime.lock) is constrained by it.
Runtime containers do not install the audit/type tooling.

Lock maintenance uses existing reviewed uv 0.11.19 via
`python scripts/ops/dependencies.py lock`, then `check`. The recorded
[baseline.constraints](../deploy/python/baseline.constraints) constrains existing
versions; it is not an installation list. Never regenerate with `pip freeze`,
remove numerical constraints or auto-fix major dependencies. Review new edges first.

For a clean offline Windows rehearsal:

```powershell
.venv/Scripts/python.exe -m pip --isolated download --index-url https://pypi.org/simple --require-hashes --only-binary=:all: -r apps/backend/requirements.lock -d .tmp/ops/wheelhouse/windows
.venv/Scripts/python.exe scripts/ops/reproduce.py --environment .tmp/ops/repro-new --wheelhouse .tmp/ops/wheelhouse/windows
```

The rehearsal refuses an existing environment and builds local wheels from
temporary source copies. Windows success is not Linux proof; CI repeats clean
installs on both platforms. CI/web/Vercel consume the root workspace lock only,
with no nested-lock fallback. The older Vite/Vitest/esbuild graph remains a
release blocker; its version/integrity checks and the required upgrade-skill
handoff are in [DEPENDENCY_REVIEWS.md](DEPENDENCY_REVIEWS.md). No install or upgrade
was performed in the 2026-09-10 concurrent-test batch. Do not run either installer
until the supervising parent finishes every shared-environment test.

### Configuration And Local Checks

[.env.example](../.env.example) contains names with empty values. Supply values
through operator-controlled process configuration; operations helpers never
read/create credential files or rotate secrets. Do not put real URL credentials,
tokens or passwords into logged commands. Setup installs only by default;
`--start-database`, `--migrate`, `--profile` and `--verify` are explicit actions.

The dev launcher `node scripts/dev.js` binds API/UI to loopback, forces Vite's
strict port, refuses production/staging, and no longer starts a database or
loads `.env`. Database startup/migrations are prerequisites. Set an explicit
`BEBSHAX_POSTGRES_PASSWORD` and matching `BEBSHAX_DATABASE_URL` when intentionally
using the local DB. Root `npm start` is now a production-only API entry point:
it requires `BEBSHAX_ENVIRONMENT=production` or `staging`, runs the same production
validator as the container, uses exactly one Uvicorn worker without reload, and
binds `127.0.0.1:8000` behind an operator-managed HTTPS proxy. It requires the
existing project virtual environment and never starts Docker or applies migrations.
It is not a process supervisor or a static frontend server. Use the built web
image or a separately reviewed static host for the frontend, never Vite dev/preview.

Canonical commands from the root:

| Command | Scope |
| --- | --- |
| `npm run dev` | Loopback API plus Vite; development only |
| `npm run dev:backend` / `npm run dev:frontend` | Separate loopback development processes |
| `npm start` | Validated production/staging API, no reload or automatic migrations |
| `npm run build` / `npm run typecheck` | Root-workspace frontend TypeScript/build |
| `npm test` | Ops, backend, ML, frontend, sequentially |
| `npm run test:ops` | Node safety checks and Python ops suite |
| `npm run test:backend` / `npm run test:ml` | Existing Python suites through project `.venv` |
| `npm run test:frontend` | Existing Vitest suite, one worker, no file parallelism |
| `npm run check:npm-graph` / `npm run check:python-lock` | Declared lock consistency; no install |

### Remote Processing Is Denied By Default

The parent-owned `remote_processing_policy: RemoteProcessingPolicy` setting is
configured with `BEBSHAX_REMOTE_PROCESSING_POLICY`, a JSON object. Omission uses
the deny-all default. This is the only example policy supplied by operations:

```json
{
	"policy_id": "deny-unapproved",
	"synthetic_providers": [],
	"private_providers": [],
	"synthetic_openrouter_upstreams": [],
	"private_openrouter_upstreams": []
}
```

Do not set the variable to an empty string; omit it or supply this valid JSON.
Compose forwards an optional operator-supplied value with no built-in approvals.
Provider keys, a provider catalog entry and `--allow-network` are not consent.
Routing-owned [providers.toml](../providers.toml) is a separate configuration;
operations does not approve providers, private clients, data or OpenRouter upstreams.

Smoke/capacity/live cross-route scripts consume this policy without modification
and scope only their built-in synthetic fixture prompts as synthetic. Empty or
private-only approval fails before adapter construction. They close adapters on
exit, do not write application provenance to the database, and are not evidence
of fleet capacity, private-data approval or a completed customer journey.

```powershell
.venv/Scripts/python.exe scripts/release_preflight.py
.venv/Scripts/python.exe scripts/ops/compose_check.py --standalone
.venv/Scripts/python.exe -m unittest discover -s scripts/tests -p "test_ops_*.py" -v
node --test scripts/tests/ops-*.test.mjs
```

Omit `--standalone` where `docker compose` is available normally. The checker
runs only both profiles' `config --quiet`, with temporary empty input and
synthetic settings. The preflight has no network/DB/model load by default; HTTP
readiness requires `--api-url` plus `--allow-network`. Live smoke/capacity/route
evaluation also require explicit network consent. No probe guarantees availability.

The historical benchmark, smoke, demo preflight and local-interview-judge entry
points now exit with retirement notices before provider/application imports.
Existing historical artifacts are retained. Current operations checks do not
certify offline live chat.

### Production Path And Artifacts

[images.json](../deploy/images.json) records verified Python/Node/nginx/pgvector
index digests. Pinning is not a CVE attestation. CI builds/scans images and
retains CycloneDX SBOMs without publishing them. The local Docker engine was
unavailable, so actual Linux/nginx/container runtime checks remain unverified.

The `full` profile is a single-process production foundation: API UID/GID 10001,
web UID/GID 101, read-only root filesystems, dropped capabilities, bounded
CPU/RAM/PIDs/tmpfs/logs, and restarts. DB network is private; DB host port 5433
and web host port 8080 are loopback-only. No API host port is published.
An approved HTTPS ingress is mandatory and is not provisioned here. Existing
named volumes are retained; never delete/reset them during rollout.

`bebshax_appdata` persists writable uploads, processed data and metadata at
`/app/data`. Set `BEBSHAX_ARTIFACT_RELEASE_DIR` to an independently approved
immutable release containing `ml_persona/model`; it is mounted read-only at
`/app/artifacts`, with missing-source auto-creation disabled. Supply the approved
`BEBSHAX_ML_PERSONA_MANIFEST_SHA256`. Stage/verify a new directory before changing
the pointer and restarting; never overwrite a live release or download/train on
startup. Integrity does not prove publisher trust or redistribution rights.
Unknown pretrained rights remain excluded. Dataset/attribution and GSAP/product
commercial acceptance are distinct release gates.

Apply the parent's single Alembic head to an explicitly selected database as a
separate reviewed release step; API boot no longer performs migrations.
Use [migrate_db.py](../scripts/migrate_db.py), not the historical auto-initializer.
Supply the direct URL through a process variable outside logged commands. For an
explicitly selected local scratch target, this command validates only, with no
connection or migration:

```powershell
.venv/Scripts/python.exe scripts/migrate_db.py --url-env BEBSHAX_MIGRATION_DATABASE_URL --confirm-target 127.0.0.1:5433/bebshax_rehearsal_test
```

Only append `--apply` after backup/recovery review and explicit target approval.
Remote targets also require `--allow-remote-target` and `verify-full` TLS; known
pooler hosts and ports 6432/6543 are rejected. Use an operator-confirmed direct
endpoint; name-based pooler detection cannot prove an unknown endpoint's mode.
No default application URL, URL command-line argument, `create_all`, stamp-only
shortcut, demo seeding or readiness claim is supported. `setup.py --migrate`
requires `--migration-url-env` and `--confirm-migration-target` before installation
starts, plus separate `--allow-remote-migration` for a remote target.

Readiness must reject stale schema or missing required models. Configured
budgets: DB probe 8s, HTTP readiness 12s, container timeout 15s, startup grace
180s; proxy idle 315s exceeds the current 300s router cap. API drain/server/
container shutdown budgets are 15/25/45s. These are not measured SLOs.

[runtime_probe.py](../deploy/runtime_probe.py) is the offline image probe used by
release CI. It checks UID/GID 10001, exact numerical package versions, real writes
to disposable files in `/tmp` and `/app/data`, and non-writable code/artifact
roots. Its unit tests do not certify an actual container or approved model bundle;
the parent must schedule the real image build/probe after concurrent tests finish.

### Origins, Sessions And Vercel

Release startup requires exact HTTPS `BEBSHAX_FRONTEND_BASE_URL`, matching CORS
with no regex, no demo mode, and a required hash-pinned model. Web always uses
same-origin `/api`. `VITE_NEON_AUTH_URL` supplies the same tenant to frontend and
backend. CSP adds only that HTTPS origin, never `*.neon.tech` or another global
wildcard; the exact Google avatar origin is added only with federation.

Vercel hosts the SPA, not API/storage/models. Unconfigured root builds fail
closed. With the same public build-time auth URL configured, generate the
committed release configuration for the actual public API host:

```powershell
node scripts/ops/web-config.mjs vercel https://bebshax-api.onrender.com
```

The generator writes the root `vercel.json`: the exact hosted API rewrite comes
before the SPA fallback, proxied `/api` responses are never CDN-cached, and CSP
matches the selected auth tenant. `build-vercel` (the committed `buildCommand`)
validates that file again at build time and forces `VITE_API_BASE=/api` and
`VITE_MOCK=0`, so a hosted build can never serve sample data. Commit the file;
no deployment is performed by the script.

Parent gates remain: server-revocable sessions, Secure/HttpOnly/SameSite cookies,
CSRF/Origin checks, callback origins, trusted proxy/IP/scheme handling, real HTTPS,
DB TLS and mail/auth authority alignment. CSP is not proof of those behaviors.

### Cloud Release Runbook (Render + Vercel + Neon)

Topology: Vercel serves the SPA and proxies same-origin `/api/*` to the Render
web service; Render runs the API image from [apps/backend/Dockerfile](../apps/backend/Dockerfile)
with the persona ML bundle baked in; Neon (ap-southeast-1) is Postgres. Every
setting below is public except the ones Render prompts for; never paste secrets
into git, tickets or chat.

**1. Neon.** Copy both connection strings for the production branch: the pooled
URL (`…-pooler.…neon.tech`) for the running API and the direct URL (same host
without `-pooler`) for migrations. Use the `postgresql://` form with
`?sslmode=require`; the engine adds the asyncpg driver itself. Before the first
deploy create a Neon branch (instant snapshot) named for the release; the
pre-deploy step applies every pending Alembic revision and refuses to start the
new API if the schema is not at head, so the branch is the rollback point.

**2. Render.** Dashboard → New → Blueprint → select this repository. Render
reads [render.yaml](../render.yaml) (service `bebshax-api`, Singapore, plan
`1c-2g`, Docker runtime, health `/api/health/ready`, deploys only when CI
checks pass). It prompts once for the `sync: false` values:
`BEBSHAX_DATABASE_URL` (pooled), `BEBSHAX_MIGRATION_DATABASE_URL` (direct),
`BEBSHAX_RESEND_API_KEY`, `BEBSHAX_EMAIL_FROM_ADDRESS` (sender on a domain
verified in Resend), `BEBSHAX_NEON_AUTH_URL` (same value as the Vercel
`VITE_NEON_AUTH_URL`, or empty to disable Google sign-in) and
`OPENROUTER_API_KEY`. `BEBSHAX_JWT_SECRET` is generated by Render. The
`preDeployCommand` runs `alembic upgrade head` inside the new image before it
receives traffic; a failed migration aborts the deploy while the previous
version keeps serving. `BEBSHAX_ML_PERSONA_MANIFEST_SHA256` in the blueprint is
`sha256(metadata.json)` of the vendored bundle and is re-derived by CI
(`backend-aux`) on every push. If the service hostname is not
`bebshax-api.onrender.com`, regenerate `vercel.json` (step above) and commit.

**3. Vercel.** Import the repository with **Root Directory = repository root**
(not `apps/frontend`; the nested config and lockfile were removed and the root
workspace lock is the only install graph). The committed `vercel.json` was
generated for the configured Neon Auth tenant, so set the Production
environment variable `VITE_NEON_AUTH_URL` to exactly that tenant URL (the host
named in the file's `connect-src`) before the first build; `build-vercel`
fails closed with "Build-time Neon configuration and CSP differ" otherwise. To
run without Google sign-in, unset it on both sides and regenerate the file with
the variable unset, then commit. Install, build and output settings come from
`vercel.json`.
The production domain must equal `BEBSHAX_FRONTEND_BASE_URL` and
`BEBSHAX_CORS_ORIGINS` in `render.yaml` (currently
`https://bebshax-frontend.vercel.app`); for a custom domain change both values,
commit, and let Render redeploy — credentialed CORS is exact-origin and a
mismatch makes every browser call fail closed.

**4. Verify.** `GET https://<api-host>/api/health/ready` returns 200
`{"status":"ready","db":"ok"}` (503 while the schema, core startup or the
required model is not validated); `GET /api/health` shows `demo_mode: false`,
`schema_validated: true`, `remote_processing.policy_id` and a `configured`
OpenRouter provider. `/docs`, `/redoc` and `/openapi.json` answer 404 in
`production` and `staging` (the schema is only served in `development`). In the
SPA: sign up with a real mailbox (the code arrives through Resend; the console
fallback exists only in `development`), sign in, create a study, generate
personas (ML bundle), run one interview (LLM route visible in provenance),
generate the report, refresh mid-flow. No "Demo mode" or "sample data" banner
may appear; if it does, the API environment is wrong, not the build.

**5. Rotate on exposure.** Any connection string that reached a terminal, log or
chat is compromised: reset the role password in the Neon console, update both
Render URL variables, redeploy. The same applies to Resend/OpenRouter keys.

**Storage boundary.** Neon holds every durable record (accounts, studies,
personas, interviews, reports, dataset metadata, statistics, discovered segments
and dataset versions). The Render filesystem under `BEBSHAX_DATA_DIR` is
ephemeral: the published row files behind dataset previews and the copilot
`query_dataset` tool disappear on every deploy or restart. Segment-based persona
generation keeps working from the stored segments; previews of earlier uploads
report zero rows until the file is uploaded again, and the API says so instead
of failing. Do not attach a Render disk to this image as-is — the service runs
as uid 10001 and cannot write a root-owned mount.

Self-hosted `docker compose --profile full` is unchanged: the image now ships
the bundle at `/app/artifacts/ml_persona/model`, and the read-only
`BEBSHAX_ARTIFACT_RELEASE_DIR` bind mount still overrides it when set.

### Backup And Restore Rehearsal

[recovery.py](../scripts/ops/recovery.py) requires PG16 clients, explicit URL
**variable names**, and exact `host:port/database` confirmations. It never loads
`.env`, uses no default URL, hides credentials/server errors, disables password
prompts, and refuses existing output paths. Pause all DB/blob writers first.
Supply a data-owner lineage index (schema version 1; dataset/persona-version/
transcript coverage; portable `storage_key`/SHA256 references; no unresolved
legacy paths). Parent M3 must export and verify this against real rows.

```powershell
.venv/Scripts/python.exe scripts/ops/recovery.py backup --source-url-env BEBSHAX_BACKUP_SOURCE_URL --confirm-source HOST:PORT/DATABASE --writers-paused --data-root deploy/recovery/source-data --artifact-root deploy/artifacts/APPROVED_RELEASE --lineage-index deploy/recovery/lineage.json --model-manifest-sha256 APPROVED_MODEL_SHA256 --output deploy/recovery/NEW_BUNDLE
.venv/Scripts/python.exe scripts/ops/recovery.py verify --bundle deploy/recovery/NEW_BUNDLE --manifest-sha256 APPROVED_BUNDLE_SHA256
.venv/Scripts/python.exe scripts/ops/recovery.py restore --target-url-env BEBSHAX_RESTORE_TARGET_URL --confirm-target 127.0.0.1:5544/bebshax_rehearsal_test --bundle deploy/recovery/NEW_BUNDLE --manifest-sha256 APPROVED_BUNDLE_SHA256 --output deploy/recovery/NEW_RESTORED_TREE
```

Place credentials in the selected process variables outside logged commands.
Restore requires an empty `bebshax_rehearsal_*` DB, refuses the source fingerprint,
and requires separate `--allow-remote-target` consent plus `verify-full` TLS for
remote targets. There is no clean/drop/overwrite option. Default budget is 1 GiB;
PG operations are timeout-bounded. Restrict filesystem ACLs and use encrypted
storage/transport; bundles contain private data and must never enter public logs.

The manifest covers dump, files, model metadata and supplied lineage. Restore
checks hashes, PG16, one revision, pgvector and validated constraints; a receipt
records elapsed time and scope. Portable keys reject Windows drive paths,
backslashes, traversal, case collisions, symlinks/junctions and device names.
Legacy-root mapping is inventory-only, never a silent DB rewrite. Synthetic
file tests are not a live cross-host restore.

Proposed targets: daily consistent backup (RPO <=24h), weekly different-host
rehearsal, RTO <=60min. These are **not measured or scheduled**. The deployment
owner must select authorized sources/targets, a lineage exporter, encrypted
storage, retention/cost and a scheduler. No host scheduler or live DB was touched.

<details>
<summary>Historical setup evidence (superseded; not current release instructions)</summary>

The material below is retained as dated evidence. Its local-provider/offline-
venue, open-range installs and automatic migrations are obsolete.

Everything needed to run BebshaX from a clean checkout. One-shot: `python scripts/setup.py` automates the base environment setup; the Persona ML lifecycle below is explicit and is not run automatically. Commands below use Windows executables; on macOS/Linux use `.venv/bin/python` and `.venv/bin/pip`, without `.exe`.

## 0. Prerequisites

| Tool           | Version    | Notes                                                                              |
| -------------- | ---------- | ---------------------------------------------------------------------------------- |
| Python         | 3.12+      | `python --version`                                                                 |
| Node.js        | 24 LTS     | `node --version` — CI and the `web` image use Node 24; 20+ still builds locally    |
| Docker Desktop | any recent | only needed for the local Postgres; a cloud Postgres URL works instead             |
| Ollama         | optional   | required only for the offline drill / local model tier (`ollama pull llama3.2:3b`) |

**Zero API keys is a supported configuration** — freellmpool starts on keyless providers. Keys added to `.env` unlock more routes. Persona selection itself is CPU-only and needs no LLM/provider key; it does need the local artifact below.

## 1. Clone

```bash
git clone https://github.com/Tayebbb/BebshaX.git
cd BebshaX
```

## 2. Python environment

```powershell
python -m venv .venv
.venv/Scripts/pip.exe install -c ml_persona/constraints.txt -e ml_persona -e "apps/backend[dev]"
```

Both editable packages are required by current backend imports. The [setup helper](../scripts/setup.py), all three Python jobs in [CI](../.github/workflows/ci.yml), and the [backend image](../apps/backend/Dockerfile) install both packages. The image also copies [ML runtime constraints](../ml_persona/constraints.txt) and applies them to both installations. The command above matches that reference-model runtime; unconstrained setup/CI environments must train their own compatible artifacts or apply the constraints before loading the reference bundle.

### Persona ML artifact

Installing the ML package does not provide a trained model. A local reference
bundle has been trained and evaluated as of 2026-09-09, but raw/processed data
and trained artifacts are ignored by Git and are not distributed in a clean
checkout. Build a compatible bundle locally before persona generation; no
production-readiness claim is implied by the recorded offline results.

From the repository root, after installing both packages:

```powershell
.venv/Scripts/python.exe -m bebshax_persona_ml download
.venv/Scripts/python.exe -m bebshax_persona_ml prepare
.venv/Scripts/python.exe -m bebshax_persona_ml validate
.venv/Scripts/python.exe -m bebshax_persona_ml train --config ml_persona/configs/training.json
.venv/Scripts/python.exe -m bebshax_persona_ml evaluate
.venv/Scripts/python.exe -m bebshax_persona_ml generate --input ml_persona/examples/business.json --num-personas 5
.venv/Scripts/python.exe -m bebshax_persona_ml smoke --backend --input ml_persona/examples/business.json
```

Only `download` needs network access; it delegates to the existing approved
`ml_persona` dataset profile. No API key, running API/DB, LLM, GPU, or PyTorch
is required for this lifecycle. `device: "cuda"` is rejected; `cpu` and `auto`
both run on CPU. Preparation, training, and evaluation outputs default under
`data/processed/ml_persona/`; generation writes JSON to stdout unless `--output`
is supplied. Existing lifecycle outputs require explicit `--force` to replace;
a normal download reuses only verified artifacts. Do not retune after inspecting
the held-out test. Full options, output paths, and recovery order are in
[ml_persona/README.md](../ml_persona/README.md).

- **Override:** `BEBSHAX_ML_PERSONA_ARTIFACT_DIR`, consumed by `Settings.ml_persona_artifact_path` in [config.py](../apps/backend/bebshax/config.py). `BEBSHAX_PERSONA_ML_MODEL_PATH` is not a supported setting alias.
- **Default:** `<processed_dir>/ml_persona/model`. The processed root is `BEBSHAX_PROCESSED_DIR` when set, otherwise `<BEBSHAX_DATA_DIR>/processed`; unchanged defaults give `data/processed/ml_persona/model`. Relative paths resolve against the backend process's working directory.
- **Explicit failures:** HTTP 503 `ml_persona_unavailable` for missing/unloadable artifacts; HTTP 422 `ml_persona_unsupported_context` when the model cannot support the requested context or constraints. See [API_CONTRACT.md](API_CONTRACT.md).
- **Module entry point:** [ml_persona/pyproject.toml](../ml_persona/pyproject.toml) declares no console script; use `python -m bebshax_persona_ml`, backed by [the CLI](../ml_persona/src/bebshax_persona_ml/cli.py). Backend startup does not download or train a model.
- **Runtime compatibility:** the saved run used Python 3.12.9, NumPy 2.5.2, SciPy 1.18.1, and scikit-learn 1.9.0. Loading requires exact NumPy/SciPy/scikit-learn matches, pinned in [constraints.txt](../ml_persona/constraints.txt). Use these constraints for the reference bundle or train a fresh bundle in the intended environment. Never edit metadata to bypass checks.
- **Reload:** the adapter loads lazily and caches the model. Restart the API after deliberately replacing a validated bundle; configure the path before startup.

`smoke --backend` checks source, prepared data, model, generation, and real
backend mappings without settings initialization, DB, network, or LLM calls.
All five stages passed on 2026-09-09; this command is not a live API/DB test.
Separate live persistence, Freellmpool interview, and offline Linux-container
checks also passed; see the [implementation report](../ml_persona/IMPLEMENTATION_REPORT.md).
The [model card](../ml_persona/MODEL_CARD.md) and
[experiment record](../ml_persona/EXPERIMENTS.md) document the USA-synthetic-only
scope and underperformance relative to lexical TF-IDF. Chat/interview LLM routing
and normal application authentication/database prerequisites are unchanged.

## 3. Secrets

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

For a new environment, set the generated value as `BEBSHAX_JWT_SECRET` in the local environment file (mandatory, ≥32 chars; the burned example value is rejected at startup). Preserve existing valid secrets, provider keys, and database settings; do not rotate them merely to set up ML. Never commit secrets (R4). JWT lifetime defaults to one day via `BEBSHAX_JWT_EXPIRE_DAYS`.

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

`ml_persona` is independent of that chain and is not fetched even by `full`.
Its approved synthetic source is for non-LLM training only, never observed
customer evidence; see [ml_persona/DATASETS.md](../ml_persona/DATASETS.md).

## 6. Verify

```powershell
.venv\Scripts\python -m pytest apps/backend/tests -q
.venv\Scripts\python -m pytest ml_persona/tests -q
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

For persona generation, the self-hosted processed-data mount must also contain
the locally built ML bundle; copying/installing the package into the image does
not supply weights. Its recorded numerical versions must match the serving
image, or a fresh bundle must be trained in the intended numerical environment.
Cloud API hosts likewise provision a compatible local bundle and configure its
artifact path. No model download or training occurs on an HTTP request. The
[post-sync local checks](../ml_persona/IMPLEMENTATION_REPORT.md#post-sync-verification-2026-09-09)
passed on 2026-09-09, including both quiet Compose syntax checks and all five
trained-artifact smoke stages. Earlier verification loaded the Windows-trained
artifact in the Linux backend image with networking disabled and exercised
separate local PostgreSQL/Freellmpool flows; these were not repeated after sync
and are not a full Compose app/web rehearsal. The earlier desktop check passed;
mobile persona-header clipping remains unfixed and was not reverified after
upstream styling or the token-only correction. Full Compose app/web and
cross-conversation retrieval rehearsals were not repeated. Commit, push, and CI
results are tracked separately in the [implementation log](IMPLEMENTATION_PLAN.md),
not claimed successful here.

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

Persona serving adds `BEBSHAX_ML_PERSONA_ARTIFACT_DIR`; its processed-root default
and restart requirement are described [above](#persona-ml-artifact). This is a
backend setting, not the standalone CLI's model selector (`--model`).

Names only — values live in `.env` (gitignored); [.env.example](../.env.example) documents every `Settings` field (a test enforces parity). Core: `BEBSHAX_APP_NAME`, `BEBSHAX_ENVIRONMENT`, `BEBSHAX_API_HOST`, `BEBSHAX_API_PORT`, `BEBSHAX_DEMO_MODE`, `BEBSHAX_LOG_LEVEL`, `BEBSHAX_CORS_ORIGINS`, `BEBSHAX_CORS_ORIGIN_REGEX` (default: localhost/127.0.0.1 on any port — deployed origins go in `BEBSHAX_CORS_ORIGINS`), `BEBSHAX_DATA_DIR` / `_UPLOAD_DIR` / `_PROCESSED_DIR`, `BEBSHAX_METADATA_DIR` (quality-gate reports for `/api/evaluation/metrics`; CWD-relative `data/metadata` by default), `BEBSHAX_DATABASE_URL`, `BEBSHAX_DB_POOL_SIZE` / `_MAX_OVERFLOW`, `BEBSHAX_JWT_SECRET`, `BEBSHAX_JWT_SECRET_PREVIOUS`, `BEBSHAX_JWT_EXPIRE_DAYS` (default 1), `BEBSHAX_JWT_ISSUER` / `_AUDIENCE` / `_ALGORITHM`, `BEBSHAX_NEON_AUTH_URL`, `BEBSHAX_REQUIRE_EMAIL_VERIFICATION`, `BEBSHAX_RATE_LIMIT_STORAGE_URI`, `BEBSHAX_RATE_LIMIT_TRUST_FORWARDED_FOR`, `BEBSHAX_EMBEDDING_BACKEND` / `_MODEL`, `BEBSHAX_RESEND_API_KEY`, `BEBSHAX_EMAIL_FROM_ADDRESS`, `BEBSHAX_FRONTEND_BASE_URL`, `BEBSHAX_SMTP_*`, `BEBSHAX_STRIPE_*`, `OLLAMA_API_BASE`. OpenRouter: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` (default model for the health check / `OpenRouterService` when no `MODEL_PERSONA|REASONING|EXTRACTION|CRITIC|BROWSER` override is set), `BEBSHAX_OPENROUTER_MODELS` (free-tier list override). Optional provider keys (each unlocks routes): `GROQ_API_KEY`, `GEMINI_API_KEY`, `NVIDIA_API_KEY`, `MISTRAL_API_KEY`, `CEREBRAS_API_KEY`, `COHERE_API_KEY`, `GITHUB_TOKEN`, `HF_TOKEN`, `CLOUDFLARE_API_TOKEN` + `_ACCOUNT_ID`. `FREELLMPOOL_CONFIG` is set automatically to the repo's `providers.toml`. Frontend build-time (baked in by Vite from the repo-root `.env`): `VITE_API_BASE`, `VITE_MOCK`, `VITE_NEON_AUTH_URL`. Not read by anything: `NEON_AUTH_BASE_URL`, `VITE_NEON_AUTH_JWKS_URL` (legacy — delete from your `.env`).

## Troubleshooting

- **503 `ml_persona_unavailable`**: installing the package alone is insufficient; check the artifact path, permissions, integrity, and exact numerical runtime versions, then build/reload a compatible bundle. There is no LLM fallback.
- **422 `ml_persona_unsupported_context`**: check input schema, vocabulary overlap, explicit age bounds, and eligible identities remaining after active-source exclusions. Role/location hints are not hard customer-fit guarantees.
- **Startup exits with a migration message** → run the alembic command from step 4; this is the drift guard doing its job (it only runs for local dev databases with demo mode off — the compose `full` profile migrates itself at start instead).
- **Signing up locally never gets a verification code** → no mail transport (`BEBSHAX_SMTP_*` / `BEBSHAX_RESEND_API_KEY`) is configured, so nothing can deliver it. With `BEBSHAX_ENVIRONMENT=development` the backend log prints `DEVELOPMENT ONLY … the verification code just issued is NNNNNN` (recipient never logged); enter that code on the verification screen. Hosted environments never print codes — configure a transport there.
- **`node scripts/dev.js` prints a red FATAL box and stops** → the backend exited non-zero (config `FATAL`, migration drift, port 8000 busy); the launcher now stops Vite too instead of serving a UI with no API. Read the `[Backend]` lines above the box.
- **`vector` type errors** → your Postgres lacks pgvector; use the compose service (port 5433) or a pgvector-enabled cloud DB.
- **Backend edits kill `node scripts/dev.js`** → uvicorn's reloader watches the repo root; finish backend edits, then restart the launcher.
- **"local tier DOWN" warning at startup** → Ollama isn't running; only the offline drill and local pool need it (`ollama serve`).

</details>
