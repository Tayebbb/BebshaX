# BebshaX — Team Assignments

## Current maintenance coordination (2026-09-09)

All original 15 phases are complete; their dates and acceptance records remain
unchanged. The phase blocks below are the historical ownership/convergence plan,
not instructions to restart completed work. Current status is in
[PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md).

Persona ML maintenance spans the independent [ML package](../ml_persona/README.md),
shared backend adapter, dataset setup, and existing business/study/role/dataset
callers. Coordinate changes across their owners; chat/interview routing, schemas,
and DB contracts remain in place. Keep tests and affected docs together, record
maintenance in the append-only [implementation log](IMPLEMENTATION_PLAN.md),
and keep the Git-ignored source data/splits/model out of commits. Final tests,
remote integration, and publication must be reported from actual results.

## Original phase ownership plan

Three parallel tracks for **Tayeb**, **Sazid**, **Shehab**. Designed so the current work block has **zero file overlap and zero cross-dependencies**: each track owns disjoint directories, and every contract a track builds against (`LLMService`, `ProvenanceRecord`, `TaskType`, persona field list, `/api/health`) is already frozen in `main` since Phases 1–3.

To do your next task, open your AI tool in this repo and say: **"Implement phase N"** (the agent follows [AGENTS.md](../AGENTS.md) + [PHASES.md](PHASES.md)).

## Original parallel block (historical)

| Teammate   | Track                  | Phases (in order)                                      | You own these paths — nobody else touches them                                                                                                                                                                      |
| ---------- | ---------------------- | ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Tayeb**  | A — LLM infrastructure | **4** (Ollama) → **5** (routing/fallback)              | `apps/backend/bebshax/llm/**`, `apps/backend/tests/llm/**`, `scripts/benchmark_ollama.py`, `scripts/smoke_*.py`, `docs/ROUTING.md`                                                                                  |
| **Sazid**  | B — Data layer         | **6** (database) → **7** (datasets)                    | `apps/backend/bebshax/db/**`, `apps/backend/alembic/**`, `apps/backend/tests/db/**`, `apps/backend/tests/datasets/**`, `scripts/setup_datasets.py`, `data/**`, `docker-compose.yml`, `apps/backend/pyproject.toml`¹ |
| **Shehab** | C — Frontend           | **12-foundation** (app shell + all views on mock data) | `apps/frontend/**`, `docs/API_CONTRACT.md`                                                                                                                                                                          |

¹ Only Track B adds Python dependencies in this block (Track A needs none — httpx is already installed). If Track A ever needs a dependency, coordinate in chat first to avoid a pyproject conflict.

**Why these can't collide or block each other:**

- A works against the frozen `ProviderAdapter`/`LLMService` contracts and Ollama's local API.
- B consumes the frozen `ProvenanceRecord` shape for `llm_requests` and builds datasets from external sources — it never imports from `bebshax.llm` internals beyond the frozen models.
- C builds against mock fixtures mirroring the frozen pydantic models; the only live endpoint it needs (`/api/health`) has existed since Phase 1.

## After the block (convergence — order matters here)

| Phase                   | Owner                                                        | Needs merged                                                                            |
| ----------------------- | ------------------------------------------------------------ | --------------------------------------------------------------------------------------- |
| 8 — Persona engine      | Tayeb                                                        | 5, 6 (7 for evidence)                                                                   |
| 9 — Memory              | ~~Sazid~~ → Tayeb (owner-approved takeover, done 2026-08-23) | 6, 8 (persona ids)                                                                      |
| 10 — Interview engine   | Tayeb (done 2026-08-23)                                      | 8 (uses 9 when ready)                                                                   |
| 11 — Quality/evaluation | Shehab                                                       | ✅ Complete (2026-08-22)                                                                |
| 12 — Frontend           | Shehab                                                       | ✅ Foundation + mock views complete (2026-08-22; live wiring follows 8/10/11 endpoints) |
| 13 — Integration + demo | all three                                                    | 10, 12                                                                                  |
| 14 — Testing hardening  | all (each hardens own track)                                 | 13                                                                                      |
| 15 — Documentation      | all (each documents own track; Tayeb assembles final report) | 14                                                                                      |

## Merge rules (prevent conflicts on shared files)

1. Work directly on `main` only inside your owned paths; anything crossing a boundary goes through a PR + a ping to the path owner.
2. `git pull --rebase` before every push. CI (pytest) must be green on `main` at all times.
3. Shared docs: the implementation log in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) is **append-only** — add your `### Phase N` block at the top, never edit others' entries. Status flips in [PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md)/[PHASES.md](PHASES.md) touch only your phase's row/heading.
4. Contract changes (anything in `bebshax/llm/types.py`, `provenance.py`, `failures.py`, `adapters/base.py`, or `docs/API_CONTRACT.md`) require agreement from all three — these are the interfaces the parallelism depends on.
5. Never commit `.env`, `data/raw/`, `data/processed/`, or `node_modules` (gitignored — keep it that way).
