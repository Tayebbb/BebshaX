# BebshaX — Final Implementation Report

Phases 1–15 complete (2026-08-22 → 2026-08-28). This report is the single summary of what was built, on what, and with which honest limitations. Deep dives: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/FAILOVER.md](docs/FAILOVER.md), [docs/MODEL_REGISTRY.md](docs/MODEL_REGISTRY.md), [docs/SETUP.md](docs/SETUP.md), [docs/DEMO.md](docs/DEMO.md), [docs/EVALUATION.md](docs/EVALUATION.md), [docs/ROUTING.md](docs/ROUTING.md), [docs/PERSONA_ENGINE.md](docs/PERSONA_ENGINE.md).

Current persona behavior includes the 2026-09-09 ML maintenance continuation below. It does not add a phase or change the original completion dates; detailed evidence and limits are in the [Persona ML report](ml_persona/IMPLEMENTATION_REPORT.md).

## 1. What was built

A synthetic-persona research platform operating on a ~zero LLM budget: business context in → locally selected synthetic source personas out → multi-turn interviews, behavioral simulations, segmentation, and reports. Every LLM call uses governed free-tier routing; persona selection itself uses a separate CPU-only learned model.

- **LLM layer**: `LLMService` abstraction with 18 task types, a closed 13-kind failure taxonomy with a per-kind policy table, 7 config-as-data pools, per-pool concurrency semaphores, persistent 60 s cooldowns, quota-aware ranking, char-based context budgeting that never truncates, and per-task latency budgets. Provider SDKs are boundary-locked to `llm/adapters/` (test-enforced).
- **Persona engine**: shared `MLPersonaAdapter` across legacy business generation, study sync/jobs/regeneration, workflow roles, and dataset generation → existing schemas and DB JSON → unchanged interview/memory services. Training learns TF-IDF vocabulary/IDF, NMF topics, and profile representations; MMR-style selection returns coherent source bundles, not new identities. All generated claims are `SYNTHETIC`, with no `OBSERVED` citations or invented income/OCEAN values. No LLM generation or fallback; unavailable models return 503 and unsupported/exhausted contexts return 422.
- **Memory**: pgvector stream (384-dim), retrieval = 0.6·cosine + 0.25·recency(48 h half-life) + 0.15·importance, reflection summarization, embedding-space consistency tags (deterministic local hash embedding by default; pinned freellmpool embedding optional).
- **Interviews**: per-turn identity composition (byte-identical identity card asserted per turn), full history or explicit `ContextWindowExceeded`, observation write-back to memory, per-turn provenance including mid-conversation provider failover.
- **Evaluation**: separate ML cross-view retrieval/structural probes and existing persona/routing evaluation. The NMF blend underperforms lexical TF-IDF; original routing replay claims were withdrawn (section 5).
- **Frontend**: single React 18 + Vite 5 + TypeScript app — cinematic landing, research console (study workflow copilot, persona library, interviews, behavioral testing, evidence lab, segmentation, model-router provenance view), light/dark semantic-token theme system with a codemod drift gate, GSAP motion system, mobile nav drawer, fluid gutters, wrap-safe grids, and demo `CACHED` badges. A mobile persona-header clipping issue remains (section 7).
- **Platform**: FastAPI + async SQLAlchemy + Alembic on Postgres 16/pgvector; JWT auth with rotation-aware secrets; slowapi rate limiting; migration drift guard; flag-gated demo seeding; provenance sink writing every LLM call to `llm_requests`.

## 2. OSS used (versions & licenses)

**Backend runtime**: fastapi ≥0.115 (MIT), uvicorn[standard] ≥0.30 (BSD-3), pydantic ≥2.7 / pydantic-settings ≥2.3 (MIT), **freellmpool ≥0.11** (MIT — the free-tier aggregation library at the heart of the routing layer), sqlalchemy[asyncio] ≥2.0 (MIT), alembic ≥1.13 (MIT), asyncpg ≥0.30 (Apache-2.0), pgvector ≥0.3 (MIT), huggingface_hub ≥0.28,<1.0 (Apache-2.0), fastparquet ≥2026.5 (Apache-2.0), python-multipart ≥0.0.9 (Apache-2.0), slowapi ≥0.1.9 (MIT), stripe ≥12 (MIT), httpx ≥0.27 (BSD-3 — declared as a runtime dependency 2026-09-06; previously reached only transitively), python-dotenv ≥1.0 (BSD-3 — same).
**Backend dev**: pytest ≥8.2, pytest-asyncio ≥0.23, pytest-cov ≥5.0, aiosqlite ≥0.20, ruff ≥0.6, pip-audit ≥2.7 (Apache-2.0, advisory CI scan).
**Frontend runtime**: react/react-dom ^18.3 (MIT), lucide-react (ISC), gsap ^3.15 + @gsap/react ^2.1 (GreenSock standard license — free for all uses since the Webflow acquisition).
**Frontend dev**: vite ^5.4 (MIT), typescript ^5.5 (Apache-2.0), vitest ^2.0 (MIT), @testing-library/\* (MIT), tailwindcss ^3.4 (MIT, preflight disabled), postcss (MIT), autoprefixer (MIT), jsdom (MIT).
**Infra**: Postgres 16 (PostgreSQL License), pgvector extension (PostgreSQL License), Ollama (MIT) with llama3.2:3b / qwen3:4b (Llama 3.2 Community License / Apache-2.0). Every dependency passed an R8 review recorded in the implementation log.

**Persona ML**: separate local package using NumPy 2.5.2, SciPy 1.18.1, and scikit-learn 1.9.0 (BSD-3-Clause), pinned in [ml_persona/constraints.txt](ml_persona/constraints.txt) for both local and Docker installs. The loader requires exact numerical-library versions. See the [R8 review and licensing limits](ml_persona/ARCHITECTURE.md); dependency licenses do not establish a project software license.

## 3. Datasets (licenses & purpose)

Existing grounding/evaluation datasets are fetched reproducibly via [scripts/setup_datasets.py](scripts/setup_datasets.py) profiles (minimal ⊂ development ⊂ evaluation ⊂ full), license-checked at download and checksummed: personahub_sample (CC-BY-NC-SA-4.0, diversity seeds — never citable as evidence), synthetic_persona_chat (CC-BY-4.0), mmlu_micro + gsm8k_micro (MIT, capability probes), amazon_reviews_office_products (UCSD academic, grounding evidence), empathetic_dialogues_slice (CC-BY-NC-4.0), router_arena (Apache-2.0) + xroute_bench (MIT) for evaluation replay, lmsys_chat_1m (gated, optional) and mbti_personality_traits (CC0) in the full profile. Full table: [data/DATASETS.md](data/DATASETS.md).

R9's owner-approved 2026-09-08 exception adds an independent `ml_persona` profile, **not included in `full`**, for reviewed public synthetic data and non-LLM training only. The current source is NVIDIA Nemotron-Personas-USA, CC-BY-4.0, pinned revision `5b4cd35ab46490c1da1bd2b5a2324d6f871be180`: 6,000 sampled rows → 4,694 schema-accepted → 3,594 complete, identity-deduplicated profiles → seed-42 train/validation/test splits of 2,516/539/539. Private studies, uploads, and conversations are excluded. **No LLM fine-tuning, ever.** Details: [ML datasets](ml_persona/DATASETS.md).

## 4. Routing / fallback architecture

LLM request → task-typed `LLMRequest` → pool (data-driven map) → ranked candidates (quota-aware) → context-window filter → cooldown filter → attempt chain under the pool's semaphore → first success, with every attempt recorded in a `ProvenanceRecord` persisted by the fail-soft sink. Failure behavior is a 13×3 policy table, cooldowns survive restarts, and local Ollama remains an interview/chat fallback (historically ~6 s/turn measured). Persona selection bypasses these pools; legacy persona-generation task enums remain for compatibility, not production persona writing. Full detail: [docs/FAILOVER.md](docs/FAILOVER.md).

## 5. Performance & evaluation results

- **Historical routing strategies** (eval_report_20260822): all 7 strategies 100 % success under chaos simulation (35 requests, scripted failures via `FakeAdapter` — synthetic, not provider data). The offline "benchmark replay" numbers previously quoted here (100 % alignment on RouterArena/xRouteBench) were **withdrawn 2026-09-06**: the replay was found unusable — the RouterArena preprocessing read columns that do not exist in the parquet (empty prompts/scores) and the xRouteBench slice carries no candidate executions, so the evaluator's default model made every strategy "align" with itself. See [docs/RESEARCH_EVIDENCE.md](docs/RESEARCH_EVIDENCE.md). HYBRID remains the shipped default on architectural grounds, not on that replay.
- **Historical live path** (2026-08-24/27 E2E audits, before ML generation): persona generation ~44 s on free cloud tiers; identity observed to hold across ovh→kilo→llm7 provider failover mid-interview in an unstored smoke run (no artifact); 2-turn interview coherent and grounded across kilo/stepfun→llm7/codestral failover at 51–73 s/turn. A formal cross-route persona-consistency evaluation was added 2026-09-06 ([scripts/run_cross_route_eval.py](scripts/run_cross_route_eval.py)). Local gate: llama3.2:3b interview quality 9.65 / 9.05 / 9.2 across three runs (n = 1 persona × 5 questions; judge model overlapped with the cloud arm in runs 1–2) at ~5–7 s/turn. These are not current ML latency or customer-quality results.
- **ML training/evaluation**: four 16/32-topic × 0.35/0.7 lexical-weight fits took 43.70 s total on two CPU threads. Selected 32/0.7 validation MRR was 0.418117 versus lexical TF-IDF 0.716645; held-out test MRR was 0.432654 versus 0.751621. The blend underperforms the baseline. All 160 probe profiles passed structural checks; exact source reuse was 100 % by design, diversity 0.877963, age JS divergence 0.030183, and 72/160 selected profiles were `not_in_workforce`. Warm five-profile p95 was 34.3 ms, excluding cold load, API, DB, and network time. See [ML experiments](ml_persona/EXPERIMENTS.md).
- **2026-09-09 live verification**: five unique age-bounded ML personas persisted and read back with synthetic claims and zero LLM generation calls. Seven successful Freellmpool responses covered copilot context, role suggestions, and two interview turns with four 384-dimensional memories; this is a smoke sample, not a provider success rate or cross-route benchmark. The Windows-trained artifact also loaded and selected five profiles in the Linux backend image with networking disabled.
- **Capacity**: ~100 personas/day on $0 was an LLM-era planning target, not measured throughput. ML selection no longer consumes LLM persona-generation quota; end-to-end study/interview capacity remains unvalidated.
- **Post-sync local verification (2026-09-09)**: 1,284 backend passed / 3 deselected (81.71 % coverage, including packaging regressions), 295 ML passed (97 %), and 269 frontend passed across 36 files before the CSS token correction. The latest TypeScript/Vite build and theme check passed after that correction. Exact scope, timings, and the preserved pre-sync baseline are in the [canonical verification record](ml_persona/IMPLEMENTATION_REPORT.md#post-sync-verification-2026-09-09). Commit, push, and CI results are tracked separately in the [implementation log](docs/IMPLEMENTATION_PLAN.md); no publication success is claimed. The original Phase 14 counts remain historical acceptance evidence below.

## 6. Security posture

JWT secrets are env-only, ≥32 chars, burned-default rejected at startup, with `_PREVIOUS` rotation support; alphanumeric password policy; flag-gated email-verification enforcement; slowapi rate limiting with deployment knobs; explicit-origin CORS; tenancy columns + shared-owner seeding for public fixtures; no secrets in code or logs (R4); prompt-injection defense in the behavioral engine; provenance never hides fallbacks. Known deferred items are listed below rather than papered over.

## 7. Limitations (honest)

- `model_registry` capability/score columns are schema-only; live discovery + quota ranking made sync jobs unnecessary at this scale ([docs/MODEL_REGISTRY.md](docs/MODEL_REGISTRY.md)).
- Persona selection is local, but chat/interviews still face free-tier latency and availability limits. The old 30–190 s cloud persona-generation range is historical, not a measurement of the ML API.
- USA-synthetic source prototypes are not validated customers, students, Bangladesh residents, or population/demand estimates. Age bounds are hard within 18–95; role/location are soft hints and never rewrite source occupation/location. No income, purchasing-power, or OCEAN measurements are invented.
- Sequential generation excludes active source IDs/names within its owner scope; there is no transactional identity lock for overlapping requests. The 160-profile probe does not establish concurrent or cross-process uniqueness.
- Model bundles are Git-ignored, about 32.54 MiB on disk, and are not supplied by a fresh CI/Compose checkout. Prepare/train or stage a trusted, numerically compatible artifact before generation. Loading is lazy/cached; restart after artifact replacement. See [ML setup](ml_persona/README.md).
- Google sign-in goes through Neon-hosted OAuth and server-verified `/api/auth/sync`; when Neon Auth is not configured the button is disabled — there is no client-side fallback identity. In mock/test builds a clearly-mock session is minted under the same gate as the mocked email flow.
- Withdrawn routing replay scores cannot establish strategy quality; ML cross-view retrieval cannot establish business relevance.
- Response caching lives inside freellmpool (surfaced via provenance notes), not as a first-party layer.
- Single-worker deployment assumptions (in-memory rate-limit storage) until `rate_limit_storage_uri` is pointed at a shared backend.
- Before upstream styling, desktop 1440×1000 rendering passed and mobile 390×844 exposed persona-header regenerate/close clipping. The initial ML continuation changed no UI code; the subsequent user-approved correction changed only four theme-token declarations in three CSS files. It neither fixes the clipping nor constitutes browser re-verification. Full Compose app/web and cross-conversation memory retrieval rehearsals were not repeated; Pyright was unavailable. This is not a production-readiness verdict.

## 8. Future work

Business-labelled persona relevance evaluation and broader reviewed source coverage; selection-bias analysis; concurrent identity guarantees; shared rate-limit storage + multi-worker topology; valid routing replay sets; measured end-to-end capacity; full Compose rehearsal and expanded browser journeys, including the known mobile header defect.

## 9. Final state

Original phase acceptance record, unchanged by ML maintenance:

| Phase | Scope                                                                                        | Status        |
| ----- | -------------------------------------------------------------------------------------------- | ------------- |
| 1–7   | Foundation, LLM abstraction, freellmpool, Ollama, routing, database, datasets                | ✅ 2026-08-22 |
| 8–10  | Persona engine, memory, interviews                                                           | ✅ 2026-08-23 |
| 11–12 | Evaluation, frontend                                                                         | ✅ 2026-08-22 |
| 13    | Integration + demo mode (flag-gated seed, cached labeling, offline drill)                    | ✅ 2026-08-28 |
| 14    | Testing hardening (acceptance matrix mapped, 423 tests)                                      | ✅ 2026-08-28 |
| 15    | Documentation (this report + ARCHITECTURE/FAILOVER/MODEL_REGISTRY/SETUP, `scripts/setup.py`) | ✅ 2026-08-28 |
