# BebshaX Demo Mode Documentation (Phase 13 / H3)

This document describes the BebshaX Demo Mode, its configuration, seeded sample entities, and the upcoming data-source transparency labeling.

---

## 1. Overview

Demo Mode provides a deterministic, self-contained baseline for showcasing BebshaX (seeded study, persona, evidence and decision report) so the tour has content before any model is called. **Only the seeded content is free of live provider calls.** Everything you generate during the tour (personas, interview turns, copilot replies, reports) is a real LLM call routed through the free-tier pools, and offline it falls through to local Ollama or fails explicitly — there is no cached-reply or mock-LLM layer in demo mode (see §6).

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

1. **Demo User:**
   - **Email:** `founder@bebshax.ai`
   - **Name:** `Sarah Chen`
   - **Role:** Founder / Study Author
   - **Auth Provider:** `email` (`is_verified=true`)

2. **Demo Business:**
   - **ID:** `biz_fintech_01`
   - **Name:** `NovaFlow Financial`
   - **Industry:** `Fintech / Personal Finance`
   - **Target Market:** `Independent contractors, rideshare drivers`
   - **Description:** Next-generation budgeting and micro-investment app for gig workers and freelancers.

3. **Grounded Persona & Evidence (one persona, `per_sarah_01`):**
   - **Persona:** `Sarah Chen` — full-time rideshare & grocery courier, age 29, Austin TX
   - **Attached to:** `study_demo_01`, labelled `data_source: "cached"`
   - **Evidence Grounding:** three attributes across OBSERVED / INFERRED / SYNTHETIC with two evidence items (`PersonaHub (Financial Segment)`, `EmpatheticDialogues & Customer Reviews`).

4. **Sample Studies & Decision Report:**
   - Four studies (`study_demo_01` … `study_demo_04`) at steps 5 / 4 / 2 / 1. Only
     `study_demo_01` is `is_demo=true` — that is the "finished example study" a
     visitor is steered to, and it owns report `rep_seed_demo_01`.
   - One provenance record (`req_seed_demo_01`).
   - **No conversations or interview turns are seeded.** The demo study's report
     says so explicitly; nothing in the seed claims an interview that did not
     happen.

---

## 4. "Cached" vs. "Live" Data Transparency

To maintain strict evaluation integrity and honesty:

- **`data_source: "cached"`**: rows written by the demo seeder (`db/seed.py`) — pre-authored baseline fixtures, never model output.
- **`data_source: "live"`**: Represents live inference passes executed against routed LLM providers or local Ollama engines.

**Backend: implemented 2026-08-27.** `personas.data_source` (migration `9f0a1b2c3d4e`) is written at creation time and returned by every persona endpoint. `save_persona()` defaults to `"live"` — every caller but the seeder arrives after real inference — and `seed_demo_data()` passes `"cached"` explicitly.

The label is **stored, not derived**. Computing it from `demo_mode` at read time would be wrong: the flag flips independently of the rows already in the table, so a demo-mode toggle would silently relabel personas that a real model produced. Guarded by `tests/db/test_data_source_labelling.py` (4 tests), including one that fails if the seeder stops labelling.

**Frontend: shipped 2026-08-27.** Cached personas render a monospace `CACHED` badge (tooltip: "Served from seeded/cached data — not generated live for this study") in the Persona Library cards, the Deep-Dive inspector header, and the workflow persona modal. Guarded by `tests/PersonaLibraryView.test.tsx`. Field semantics are frozen in [API_CONTRACT.md](API_CONTRACT.md).

---

## 5. Demo Walkthrough Script

Run each step in order from the repo root on the demo machine. Steps 1–4 are one-time setup; the tour itself is 5–10.

1. **Database up + migrated**
   ```powershell
   docker compose up -d db
   cd apps/backend; ..\..\.venv\Scripts\python -m alembic upgrade head; cd ..\..
   ```
2. **Enable demo mode** — in `.env` (repo root): `BEBSHAX_DEMO_MODE=true`. No API keys are required (keyless providers are a supported configuration).
3. **Start both servers**: `node scripts/dev.js` → backend on `:8000`, frontend on `:5173`.
4. **Confirm seeding**: `GET http://localhost:8000/api/health` reports `"demo_mode": true`; startup logs show the demo seed ran (skipped when the tables already hold data).
5. **Sign in** at `http://localhost:5173` with the seeded demo fixture `founder@bebshax.ai` / `Password123!` (a flag-gated demo credential defined in `db/seed.py`, not a secret). Do **not** use "Continue with Google" at the offline venue — it needs the internet. To disable the button (greyed out with an explanatory tooltip), set `VITE_NEON_AUTH_URL=` (explicitly empty) in the **repo-root `.env`** (Vite reads it there via `envDir` in `apps/frontend/vite.config.ts`; `.env.demo` already ships this line) and restart the frontend.
6. **Persona Library** — the seeded persona **Nusrat Jahan** (24, BBA undergraduate, Mohammadpur — the customer of *ShomoySuchi*, a BDT-priced student academic planner) renders with the `CACHED` badge; open the profile: the per-claim provenance chips (OBSERVED / INFERRED / SYNTHETIC) come from `coerce_provenance`, exactly like live personas. OBSERVED claims cite **real** records from `data/processed/amazon_reviews_office_products.jsonl` (reviewers outside Bangladesh — the persona carries an explicit evidence-scope note saying so); if that corpus is absent at seed time every citation is stripped and the claims are stored as INFERRED with a warning. The seed stores no personality scores and **no** `llm_requests` rows — the Routing & Provenance table is empty until a live call happens. The **Memory** tab is empty until the persona is interviewed.
7. **Studies / workflow** — open `study_demo_01` (*Customer Discovery Study*, read-only example): title, goal, prompt, step and status restore from the database and the stepper navigates all 5 steps. Its Step-2 persona card is the **same** Nusrat Jahan payload (one serializer feeds both views, so the chips agree). The study ends on a decision report labelled simulated that says explicitly no interviews were run. (No copilot transcript, roles or script are seeded — Step 1's chat is empty until you type.)
8. **Live generation (network available)** — create a new study and generate personas: routed through the free-tier pools, results labeled `data_source: "live"`, provenance visible under Routing & Provenance.
9. **Routing & Provenance view** — per-request provenance (candidates, failures, served_by, latency, tokens) proves nothing is hidden behind the demo.
10. **Judge Lab** (same view, panel below the provenance table; visible only when `BEBSHAX_DEMO_MODE=true` or the environment is development/local; sign-in required) — labelled **SIMULATED**: each button builds a throwaway `PoolRouter` over scripted `FakeAdapter` routes and runs the REAL routing code (eligibility filter, failure policies, cooldowns, provenance), never a real provider. Seven scenarios (`GET /api/demo-lab/scenarios`, `POST /api/demo-lab/scenarios/{name}/run`): `provider_429_fallback`, `provider_5xx_fallback`, `all_providers_down`, `context_overflow` (refuses, never truncates — R2), `prompt_injection` (untrusted-block wrapping + code-enforced provenance downgrade), `evidence_conflict`, `insufficient_evidence` (0 % grounding shown honestly). Every payload carries `"simulated": true`; nothing is written to the provenance sink.

### Recommended 5-minute sequence (judges)

1. **Open** `http://localhost:5173` (dev) or `http://localhost:8080` (compose `full`), sign in as `founder@bebshax.ai`.
2. **Demo study** — open `study_demo_01`: the `CACHED` badge and the simulated-report label show what is seeded vs. generated.
3. **Evidence Lab** — show the grounding corpus behind the personas (real dataset slices, not prose).
4. **Persona provenance chips** — Persona Library → Deep-Dive: every claim is OBSERVED / INFERRED / SYNTHETIC, enforced in code.
5. **One interview turn** — Interviews → ask one question: point at the **Route disclosure** (which provider/model actually served), the **Recalled memories** the persona used, and the **consistency chips** (identity drift / numeric contradiction — deterministic quality checks; a clean turn shows none). Every error surface carries a copyable **Request ID**.
6. **Routing & Provenance** — the attempts timeline for that turn (every candidate, failure kind, cooldown, served_by) and the **Evaluation card** (pool success/fallback/latency/grounding from real `llm_requests` rows).
7. **Judge Lab** — run `all_providers_down` (explicit `AllCandidatesFailed` with the full trail, no fabricated answer) and `context_overflow` (refused before any call — nothing truncated).
8. **Step 5 — "Validate with real customers"** — the report's closing card lists the SYNTHETIC/INFERRED claims a founder must still test with humans. End on that — and on the stored cross-route artifact ([RESEARCH_EVIDENCE.md](RESEARCH_EVIDENCE.md): identity retained 16/16 across three real models, n small and stated). The product de-risks research, it does not replace customers.

## 6. Offline Drill (network unplugged)

What keeps working with **no internet**:

- **Everything seeded** — the cached persona, the four studies, the decision report and its evidence render from Postgres; the UI labels them `CACHED`. Steps 5–7 and 9 of the walkthrough run unchanged. (No interview transcripts are seeded — those come from a live run.)
- **Live generation** falls back through the routing ladder: remote pools fail fast (connection errors → cooldowns) and the `local` / `emergency` pools serve via **Ollama** (`llama3.2:3b` primary, `qwen3:4b` secondary — both fit the 4 GB dev GPU). Requires the Ollama daemon: `ollama serve`, verify with `ollama list`.
- **Without Ollama**, live generation fails **explicitly** (`AllCandidatesFailed` surfaced as an error turn in the chat UI) — never silently, and cached content is unaffected. Low quality or unavailability is reported, not masked (R2).

Drill checklist: disable networking → restart `node scripts/dev.js` → walk steps 5–7 → attempt one live generation and confirm either an Ollama-served reply (daemon up) or an explicit, labeled failure (daemon down).

**Order matters — copy `.env.demo` → `.env` BEFORE building the web image or `npm run build`.** Vite inlines `VITE_NEON_AUTH_URL` (and `VITE_API_BASE`) into `apps/frontend/dist` at build time; a bundle built while a personal Neon tenant URL was in `.env` keeps that URL no matter what `.env` says later, so the "Continue with Google" button would be live — and dead without internet — at the venue. The dev server (`node scripts/dev.js`) reads `.env` live, so this only bites built bundles (`apps/frontend/dist`, the `web` image). Rebuild after switching: `cd apps/frontend; npm run build` or `docker compose --profile full build web`.

**Automated gate:** run `.\.venv\Scripts\python scripts\demo_preflight.py --strict-offline` from the repo root — it verifies every precondition above (env → local db → migrations → seed → `data/processed` has grounding jsonl → Ollama models → running backend) with ✓/✗ per check and exits non-zero if the machine is not demo-ready. `--strict-offline` additionally scans variable NAMES for cloud keys, `*_URL` hosts for non-local endpoints, and **`apps/frontend/dist` for a baked Neon tenant string** (`neonauth` / `neon.tech`) — a hit means "rebuild the bundle", and the check prints file paths only, never the URL.

## 7. Production profile (containerized deploy)

A one-command containerized deployment — the `web` image builds the SPA (with `VITE_API_BASE=/api`) and serves it via nginx; the `app` image runs the backend:

1. Copy `.env.demo` over `.env` first (§6 — build args are read from it), then `docker compose --profile full up --build -d` → open `http://localhost:8080`. Startup order is health-gated: `db` (pg_isready) → `app` (runs `alembic upgrade head`, then uvicorn; healthy when `/api/health` answers) → `web` (nginx, healthy when `/` answers). Both app containers `restart: unless-stopped`, so after a crash or a machine restart they come back on their own as soon as Docker Desktop is running again — no manual `up`. nginx proxies `/api` → `app`, keeps SSE unbuffered, and sets `X-Frame-Options`/`nosniff`/`Referrer-Policy`/`Permissions-Policy` plus a same-origin CSP on the SPA. Host Ollama is reachable via `host.docker.internal`.
2. Requires `BEBSHAX_JWT_SECRET` in `.env` (passed through via `env_file`); the database URL is overridden to the in-network `db:5432` automatically.
3. Grounding evidence is **not** in the image (`.dockerignore` excludes `data/`); compose bind-mounts `./data/processed` and `./data/metadata` read-only into `app`, so run `.venv\Scripts\python scripts\setup_datasets.py --profile minimal` on the host once (needs internet) or the EvidenceStore is empty and every claim comes out SYNTHETIC.
4. Verify with `docker compose --profile full ps` (all three `healthy`) and the preflight gate; tear down with `docker compose --profile full down`.

The first `--build` needs internet (`pip install`, `npm ci`, base images) — rehearse it before demo day; afterwards `up -d` without `--build` runs offline.
