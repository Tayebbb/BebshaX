# BebshaX Demo Mode Documentation (Phase 13 / H3)

This document describes the BebshaX Demo Mode, its configuration, seeded sample entities, and the upcoming data-source transparency labeling.

---

## 1. Overview

Demo Mode provides a deterministic, self-contained environment for showcasing BebshaX capabilities (synthetic persona generation, grounded interviews, research synthesis, and report generation) without requiring live external provider API calls or manual initial setup.

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

- **`data_source: "cached"`**: Represents responses served directly from pre-seeded baseline fixtures or deterministic local mock pools.
- **`data_source: "live"`**: Represents live inference passes executed against routed LLM providers or local Ollama engines.

**Backend: implemented 2026-08-27.** `personas.data_source` (migration `9f0a1b2c3d4e`) is written at creation time and returned by every persona endpoint. `save_persona()` defaults to `"live"` — every caller but the seeder arrives after real inference — and `seed_demo_data()` passes `"cached"` explicitly.

The label is **stored, not derived**. Computing it from `demo_mode` at read time would be wrong: the flag flips independently of the rows already in the table, so a demo-mode toggle would silently relabel personas that a real model produced. Guarded by `tests/db/test_data_source_labelling.py` (4 tests), including one that fails if the seeder stops labelling.

**Frontend: shipped 2026-08-27.** Cached personas render a monospace `CACHED` badge (tooltip: "Served from seeded/cached data — not generated live for this study") in the Persona Library cards, the Deep-Dive inspector header, and the workflow persona modal. Guarded by `tests/PersonaLibraryView.test.tsx`. Field semantics are frozen in [API_CONTRACT.md](API_CONTRACT.md).

---

## 5. Demo Walkthrough Script

Run each step in order from the repo root on the demo machine. Steps 1–4 are one-time setup; the tour itself is 5–9.

1. **Database up + migrated**
   ```powershell
   docker compose up -d db
   cd apps/backend; ..\..\.venv\Scripts\python -m alembic upgrade head; cd ..\..
   ```
2. **Enable demo mode** — in `.env` (repo root): `BEBSHAX_DEMO_MODE=true`. No API keys are required (keyless providers are a supported configuration).
3. **Start both servers**: `node scripts/dev.js` → backend on `:8000`, frontend on `:5173`.
4. **Confirm seeding**: `GET http://localhost:8000/api/health` reports `"demo_mode": true`; startup logs show the demo seed ran (skipped when the tables already hold data).
5. **Sign in** at `http://localhost:5173` with the seeded demo fixture `founder@bebshax.ai` / `Password123!` (a flag-gated demo credential defined in `db/seed.py`, not a secret). Do **not** use "Continue with Google" at the offline venue — it needs the internet. To disable the button (greyed out with an explanatory tooltip), set `VITE_NEON_AUTH_URL=` (explicitly empty) in the **repo-root `.env`** (Vite reads it there via `envDir` in `apps/frontend/vite.config.ts`; `.env.demo` already ships this line) and restart the frontend.
6. **Persona Library** — the seeded grounded persona renders with the `CACHED` badge; open the Deep-Dive inspector: profile, Big-Five, evidence citations, provenance classes (OBSERVED / INFERRED / SYNTHETIC) all populate from the seed.
7. **Studies / workflow** — open the seeded study: copilot transcript, roles, and script restore from the database; stepper navigates all 5 steps. `study_demo_01` ends on a real decision report; it seeds no interviews and its report says so.
8. **Live generation (network available)** — create a new study and generate personas: routed through the free-tier pools, results labeled `data_source: "live"`, provenance visible under Model Router.
9. **Model Router view** — per-request provenance (candidates, failures, served_by, latency, tokens) proves nothing is hidden behind the demo.

## 6. Offline Drill (network unplugged)

What keeps working with **no internet**:

- **Everything seeded** — the cached persona, the four studies, the decision report and its evidence render from Postgres; the UI labels them `CACHED`. Steps 5–7 and 9 of the walkthrough run unchanged. (No interview transcripts are seeded — those come from a live run.)
- **Live generation** falls back through the routing ladder: remote pools fail fast (connection errors → cooldowns) and the `local` / `emergency` pools serve via **Ollama** (`llama3.2:3b` primary, `qwen3:4b` secondary — both fit the 4 GB dev GPU). Requires the Ollama daemon: `ollama serve`, verify with `ollama list`.
- **Without Ollama**, live generation fails **explicitly** (`AllCandidatesFailed` surfaced as an error turn in the chat UI) — never silently, and cached content is unaffected. Low quality or unavailability is reported, not masked (R2).

Drill checklist: disable networking → restart `node scripts/dev.js` → walk steps 5–7 → attempt one live generation and confirm either an Ollama-served reply (daemon up) or an explicit, labeled failure (daemon down).

**Automated gate:** run `.\.venv\Scripts\python scripts\demo_preflight.py --strict-offline` from the repo root — it verifies every precondition above (env → local db → migrations → seed → Ollama models → running backend) with ✓/✗ per check and exits non-zero if the machine is not demo-ready.

## 7. Production profile (containerized deploy)

A one-command containerized deployment — the `web` image builds the SPA (with `VITE_API_BASE=/api`) and serves it via nginx; the `app` image runs the backend:

1. `docker compose --profile full up --build -d` → open `http://localhost:8080` (nginx proxies `/api` → the `app` container; the db healthcheck gates backend startup; host Ollama is reachable via `host.docker.internal`).
2. Requires `BEBSHAX_JWT_SECRET` in `.env` (passed through via `env_file`); the database URL is overridden to the in-network `db:5432` automatically. Tear down with `docker compose --profile full down`.
