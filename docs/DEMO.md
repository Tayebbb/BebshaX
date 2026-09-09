# BebshaX Demo Mode Documentation (Phase 13 / H3)

This document describes the BebshaX Demo Mode, its configuration, seeded sample entities, and stored data-source labels. Persona-generation guidance includes the 2026-09-09 ML maintenance update; original Phase-13 acceptance dates are unchanged.

---

## 1. Overview

Demo Mode provides a deterministic baseline (seeded study, persona, evidence and decision report) before any model is called. **Seeded fixtures are cached; new persona selection uses the local CPU ML model with no LLM call.** Copilot, interview, and report LLM work still uses governed routing and may use local Ollama or fail explicitly. Demo mode does not turn live failures into cached replies. New ML profiles remain synthetic USA source prototypes, not observed customers or validated local-market matches.

---

## 2. Configuration & Enabling Demo Mode

Demo Mode is controlled via the `BEBSHAX_DEMO_MODE` environment variable.

### In `.env` / Environment:

```bash
# Enable demo mode
BEBSHAX_DEMO_MODE=true
```

When `BEBSHAX_DEMO_MODE=false` (default in production and clean development), automatic demo data seeding is skipped on app startup.

---

## 3. Seeded Entities

When `BEBSHAX_DEMO_MODE=true` and the database is unpopulated (or when `seed_demo_data(sessionmaker, force=True)` is called), the following known-good baseline entities are seeded:

1. **Demo user:** `founder@bebshax.ai`, a verified email fixture for the flag-gated demo login.
2. **Demo business:** `biz_shomoysuchi_01`, ShomoySuchi, the student academic-planner example.
3. **Cached persona:** `per_demo_nusrat_01`, Nusrat Jahan, attached to `study_demo_01`. This pre-authored fixture is not an ML-generated population match. Its observed citations depend on real review records present at seed time; absent citations are downgraded. No personality measurements are seeded.
4. **Studies/report:** four studies (`study_demo_01` … `study_demo_04`) at steps 5 / 4 / 2 / 1; only `study_demo_01` is the demo example and owns `rep_seed_demo_01`. No conversations, interview turns, or `llm_requests` rows are seeded. The report explicitly labels its simulated basis.

Source: [db/seed.py](../apps/backend/bebshax/db/seed.py). Cached fixture claims and new ML-selected profile claims have different origins; do not present the fixture as a trained-model result.

---

## 4. "Cached" vs. "Live" Data Transparency

To maintain strict evaluation integrity and honesty:

- **`data_source: "cached"`**: rows written by the demo seeder (`db/seed.py`) — pre-authored baseline fixtures, never model output.
- **`data_source: "live"`**: Newly generated application output, including local ML persona selection. It does not mean an LLM was called, a provider was reachable, or a claim is observed evidence.

**Backend: implemented 2026-08-27.** `personas.data_source` (migration `9f0a1b2c3d4e`) is written at creation time and exposed by study-scoped persona responses; the legacy `PersonaProfile` response does not include it. `save_persona()` defaults to `"live"`, including ML selections, and `seed_demo_data()` passes `"cached"` explicitly. See [API_CONTRACT.md](API_CONTRACT.md).

The label is **stored, not derived**. Computing it from `demo_mode` at read time would be wrong: the flag flips independently of the rows already in the table, so a demo-mode toggle would silently relabel personas that a real model produced. Guarded by `tests/db/test_data_source_labelling.py` (4 tests), including one that fails if the seeder stops labelling.

**Frontend: shipped 2026-08-27.** Cached personas render a monospace `CACHED` badge (tooltip: "Served from seeded/cached data — not generated live for this study") in the Persona Library cards, the Deep-Dive inspector header, and the workflow persona modal. Guarded by `tests/PersonaLibraryView.test.tsx`. Field semantics are frozen in [API_CONTRACT.md](API_CONTRACT.md).

---

## 5. Demo Walkthrough Script

Run each step in order from the repo root on the demo machine. Steps 1–4 are one-time setup; the tour itself is 5–10.

First complete [SETUP.md](SETUP.md), including the constrained two-package
installation and [ML artifact lifecycle](SETUP.md#persona-ml-artifact). Package
installation or the `minimal` dataset profile alone does not provide the model.
On an already trained checkout, check it without network/DB/LLM calls:

```powershell
.venv/Scripts/python.exe -m bebshax_persona_ml smoke --backend --input ml_persona/examples/business.json
```

1. **Database up + migrated**
   ```powershell
   docker compose up -d db
   cd apps/backend; ..\..\.venv\Scripts\python -m alembic upgrade head; cd ..\..
   ```
2. **Enable demo mode** — in `.env` (repo root): `BEBSHAX_DEMO_MODE=true`. No API keys are required (keyless providers are a supported configuration).
3. **Start both servers**: `node scripts/dev.js` → backend on `:8000`, frontend on `:5173`.
4. **Confirm seeding**: `GET http://localhost:8000/api/health` reports `"demo_mode": true`; startup logs show the demo seed ran (skipped when the tables already hold data).
5. **Sign in** at `http://localhost:5173` with the seeded demo fixture `founder@bebshax.ai` / `Password123!` (a flag-gated demo credential defined in `db/seed.py`, not a secret). Do **not** use "Continue with Google" at the offline venue — it needs the internet. To disable the button (greyed out with an explanatory tooltip), set `VITE_NEON_AUTH_URL=` (explicitly empty) in the **repo-root `.env`** (Vite reads it there via `envDir` in `apps/frontend/vite.config.ts`; `.env.demo` already ships this line) and restart the frontend.
6. **Persona Library** — the seeded persona **Nusrat Jahan** (24, BBA undergraduate, Mohammadpur — the customer of _ShomoySuchi_, a BDT-priced student academic planner) renders with the `CACHED` badge; open the profile: the per-claim provenance chips (OBSERVED / INFERRED / SYNTHETIC) come from `coerce_provenance`, exactly like live personas. OBSERVED claims cite **real** records from `data/processed/amazon_reviews_office_products.jsonl` (reviewers outside Bangladesh — the persona carries an explicit evidence-scope note saying so); if that corpus is absent at seed time every citation is stripped and the claims are stored as INFERRED with a warning. The seed stores no personality scores and **no** `llm_requests` rows — the Routing & Provenance table is empty until a live call happens. The **Memory** tab is empty until the persona is interviewed.
7. **Studies / workflow** — open `study_demo_01` (_Customer Discovery Study_, read-only example): title, goal, prompt, step and status restore from the database and the stepper navigates all 5 steps. Its Step-2 persona card is the **same** Nusrat Jahan payload (one serializer feeds both views, so the chips agree). The study ends on a decision report labelled simulated that says explicitly no interviews were run. (No copilot transcript, roles or script are seeded — Step 1's chat is empty until you type.)
8. **Live ML generation (artifact required)** — create a study through the existing copilot, then generate its panel. The four persona-generation paths use local TF-IDF/NMF source selection, label results `data_source: "live"`, and persist synthetic source/model provenance with the profiles, not as LLM requests. Source occupation/location remains unchanged; missing budget/OCEAN stays unknown. Only explicit age bounds are hard. No suitable batch yields 422; unavailable model yields 503, with no LLM fallback.
9. **Routing & Provenance view** — inspect LLM requests for copilot/interview/report calls (candidates, failures, served_by, latency, tokens). No LLM-generation row is expected for local ML selection; inspect the profile's source/model provenance instead.
10. **Judge Lab** (same view, panel below the provenance table; visible only when `BEBSHAX_DEMO_MODE=true` or the environment is development/local; sign-in required) — labelled **SIMULATED**: each button builds a throwaway `PoolRouter` over scripted `FakeAdapter` routes and runs the REAL routing code (eligibility filter, failure policies, cooldowns, provenance), never a real provider. Seven scenarios (`GET /api/demo-lab/scenarios`, `POST /api/demo-lab/scenarios/{name}/run`): `provider_429_fallback`, `provider_5xx_fallback`, `all_providers_down`, `context_overflow` (refuses, never truncates — R2), `prompt_injection` (untrusted-block wrapping + code-enforced provenance downgrade), `evidence_conflict`, `insufficient_evidence` (0 % grounding shown honestly). Every payload carries `"simulated": true`; nothing is written to the provenance sink.

### Recommended 5-minute sequence (judges)

1. **Open** `http://localhost:5173` (dev) or `http://localhost:8080` (compose `full`), sign in as `founder@bebshax.ai`.
2. **Demo study** — open `study_demo_01`: the `CACHED` badge and the simulated-report label show what is seeded vs. generated.
3. **Evidence Lab** — distinguish research evidence from training-source attribution; a retrieved source profile is not observed customer evidence.
4. **Persona provenance chips** — compare the `CACHED` fixture with a newly selected ML profile: its claims are `SYNTHETIC` with no observed citations. The selector preserves source identity, not an invented Bangladesh/student/budget profile.
5. **One interview turn** — Interviews → ask one question: point at the **Route disclosure** (which provider/model actually served), the **Recalled memories** the persona used, and the **consistency chips** (identity drift / numeric contradiction — deterministic quality checks; a clean turn shows none). Every error surface carries a copyable **Request ID**.
6. **Routing & Provenance** — the attempts timeline for that turn (every candidate, failure kind, cooldown, served_by) and the **Evaluation card** (pool success/fallback/latency/grounding from real `llm_requests` rows).
7. **Judge Lab** — run `all_providers_down` (explicit `AllCandidatesFailed` with the full trail, no fabricated answer) and `context_overflow` (refused before any call — nothing truncated).
8. **Step 5 — "Validate with real customers"** — the report's closing card lists the SYNTHETIC/INFERRED claims a founder must still test with humans. End on that — and on the stored cross-route artifact ([RESEARCH_EVIDENCE.md](RESEARCH_EVIDENCE.md): identity retained 16/16 across three real models, n small and stated). The product de-risks research, it does not replace customers.

## 6. Offline Drill (network unplugged)

What keeps working with **no internet**:

- **Everything seeded** — the cached persona, the four studies, the decision report and its evidence render from Postgres; the UI labels them `CACHED`. Steps 5–7 and 9 of the walkthrough run unchanged. (No interview transcripts are seeded — those come from a live run.)
- **Persona selection** works offline with a compatible local ML bundle and supported context; it does not need Ollama or provider keys. Without the bundle it fails with 503 `ml_persona_unavailable`; unsupported/exhausted context fails with 422 `ml_persona_unsupported_context`. No LLM fallback supplies missing profiles.
- **LLM work** (copilot/interview/report) still needs an eligible route. Local Ollama can serve when its daemon/model is available: `ollama serve`, then `ollama list`. Without any eligible route, LLM calls fail explicitly; cached content and the independent selector are unaffected.

Drill checklist: stage the ML bundle and local LLM first → disable networking → restart `node scripts/dev.js` → inspect cached content → select personas from supported context → separately attempt an interview and check its actual route or explicit failure. An ML smoke pass alone is not a whole-workflow offline rehearsal.

**Order matters: configure a dedicated local demo environment before building the web image or running `npm run build`.** Use the demo environment example as a reference, not as an overwrite of personal secrets or cloud database settings. Vite inlines `VITE_NEON_AUTH_URL` and `VITE_API_BASE`; an already-built bundle retains its previous values. Set the intended local endpoints and an empty `VITE_NEON_AUTH_URL` for the offline venue, preserve a valid JWT secret, and rebuild with `cd apps/frontend; npm run build` or `docker compose --profile full build web`.

**Existing preflight:** run `.\.venv\Scripts\python scripts\demo_preflight.py --strict-offline` from the repo root. It checks the local environment, DB/migrations/seed, grounding JSONL, Ollama models, and API health; it does **not** load or validate the ML artifact. Run the separate ML smoke above as well. `--strict-offline` scans variable names for cloud keys, URL hosts for remote endpoints, and the frontend build for baked Neon tenant markers, reporting paths rather than secrets. Use an isolated demo environment; do not delete personal keys to satisfy the scan.

## 7. Production profile (containerized deploy)

A one-command containerized deployment — the `web` image builds the SPA (with `VITE_API_BASE=/api`) and serves it via nginx; the `app` image runs the backend:

1. Configure the dedicated local demo environment first (§6), preserving existing secrets/settings elsewhere, then `docker compose --profile full up --build -d` → open `http://localhost:8080`. Startup order is health-gated: `db` (pg_isready) → `app` (migrations then uvicorn) → `web` (nginx). App/web restart `unless-stopped`; nginx proxies `/api`, keeps SSE unbuffered, and sets browser security headers/CSP. Host Ollama is reached via `host.docker.internal`.
2. Requires `BEBSHAX_JWT_SECRET` in `.env` (passed through via `env_file`); the database URL is overridden to the in-network `db:5432` automatically.
3. Grounding evidence and ML weights are **not** in the image. Compose bind-mounts processed data and metadata read-only. Fetch grounding datasets with `.venv\Scripts\python scripts\setup_datasets.py --profile minimal`; separately prepare/train or stage the ML bundle using §5. `full` also excludes the independent `ml_persona` profile. The image installs both packages using [numerical constraints](../ml_persona/constraints.txt); exact loader versions must match. New ML profile claims are synthetic even when grounding datasets are present.
4. Verify with `docker compose --profile full ps` (all three `healthy`) and the preflight gate; tear down with `docker compose --profile full down`.

The first `--build` needs internet (`pip install`, `npm ci`, base images) — rehearse it before demo day; afterwards `up -d` without `--build` runs offline.

**Recorded continuation scope (2026-09-09):** local ML/backend smoke,
PostgreSQL persistence, seven real Freellmpool responses, and Linux inference
from the Windows artifact with networking disabled passed. Desktop 1440×1000
passed; mobile 390×844 clipped the existing persona-header regenerate/close
controls. Full Compose app/web rehearsal and cross-conversation memory retrieval
were not run. These are not an all-green UI or production-readiness verdict;
see [ML verification](../ml_persona/IMPLEMENTATION_REPORT.md).
