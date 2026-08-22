# BebshaX — Executable Phase Specs

The authoritative definition of each phase. An agent given "implement phase N" executes the matching section below under the Phase Execution Protocol in [AGENTS.md](../AGENTS.md). Statuses here must always match the roadmap in [PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md).

**15 phases total.** Track ownership: [TEAM_ASSIGNMENTS.md](TEAM_ASSIGNMENTS.md).

Verification shorthand used below (run from repo root, Windows):
- `TESTS` = `.venv\Scripts\python -m pytest apps/backend/tests -q` → must end `passed`
- `LOCK` = if pyproject changed: `.venv\Scripts\pip freeze --exclude-editable > apps/backend/requirements.lock`

---

## Phase 1 — Foundation ✅ (2026-08-22)
Backend skeleton, `BEBSHAX_*` config, health endpoint, pytest, pgvector compose file, docs. See implementation log.

## Phase 2 — LLM abstraction ✅ (2026-08-22)
`bebshax.llm`: `LLMService`, 16 `TaskType`s, closed failure taxonomy (quality excluded), `ProvenanceRecord`, adapter boundary, `FakeAdapter`. See implementation log.

## Phase 3 — freellmpool integration ✅ (2026-08-22)
`FreellmpoolAdapter` (sole SDK importer), `AdapterCompletion` concrete-route provenance, error mapping, keyless smoke passed, Gate B (LiteLLM) skipped. See implementation log + docs/ROUTING.md.

---

## Phase 4 — Ollama integration ✅ (2026-08-22, track A)

**Goal:** local Ollama becomes a working reliability-fallback backend behind the adapter boundary.
**Prerequisites:** Phase 3 ✅. Ollama installed locally (skip live steps gracefully if the daemon is down — unit tests must not need it).
**Allowed paths:** `apps/backend/bebshax/llm/adapters/ollama_adapter.py`, `apps/backend/tests/llm/`, `scripts/benchmark_ollama.py`, `scripts/smoke_ollama.py`, docs listed below.

Steps:
1. Write `scripts/benchmark_ollama.py`: detect daemon (`OLLAMA_API_BASE`, default `http://localhost:11434`), list installed models, measure per model: time-to-first-token, tokens/sec, total latency on a short prompt (3 runs, report median). Print a table; write results to `data/metadata/ollama_benchmark.json`.
2. Run it against installed `qwen3.5:latest`. Based on measured results AND the 4 GB VRAM ceiling, recommend ONE additional ≤4B fast model (e.g. a 3–4B instruct); pull it only after printing the recommendation, then benchmark it too.
3. Implement `OllamaAdapter(ProviderAdapter)` using `httpx` directly against Ollama's OpenAI-compatible `/v1/chat/completions` (no new SDK dependency — R8): `candidates()` from `/api/tags` (one `RouteCandidate` per installed model, honest context windows from model metadata, cached briefly); map errors (connect → `CONNECTION`, timeout → `TIMEOUT`, 404 model → `MODEL_UNAVAILABLE`, 5xx → `SERVER_ERROR`, empty → `MALFORMED_RESPONSE`); return `AdapterCompletion` with real model name and token counts when Ollama reports them.
4. Unit tests with a stubbed httpx transport (`httpx.MockTransport`): success mapping, each error mapping, candidates parsing. No network, no daemon.
5. `scripts/smoke_ollama.py` mirroring the freellmpool smoke (real local call; not part of unit suite).

**Exit criteria:** TESTS green (new adapter tests included); boundary test still passes; live smoke serves a local completion when the daemon runs; benchmark JSON exists with ≥1 model measured.
**Docs to update:** docs/ROUTING.md (Ollama section: chosen models + benchmark numbers), implementation log, status flips.
**Out of scope:** router changes (Phase 5), model registry persistence (Phase 6).

---

## Phase 5 — Routing / fallback across adapters ✅ (2026-08-22, track A)

**Goal:** replace `SingleAdapterLLMService` as the production entry point with a task→pool router spanning freellmpool + Ollama.
**Prerequisites:** Phase 4 ✅.
**Allowed paths:** `apps/backend/bebshax/llm/` (new: `pools.py`, `router.py`, `estimator.py`), `apps/backend/tests/llm/`, docs listed below.

Steps:
1. Pools as data (pydantic models loaded from a checked-in `pools.toml` or Python constants — config, not code branches): `reasoning`, `conversation`, `long_context`, `structured`, `fast`, `local`, `emergency`. Each pool: ordered adapter/candidate preferences + `max_concurrency`.
2. Task→pool map covering ALL 16 `TaskType`s (unit test enforces exhaustiveness). Example: PERSONA_GENERATION/CRITIC/CONTRADICTION_CHECK → reasoning; PERSONA_INTERVIEW/PERSONA_RESPONSE → conversation; STRUCTURED_OUTPUT/EVIDENCE_* → structured; MEMORY_* → fast; EMERGENCY_FALLBACK → emergency (local-first).
3. `PoolRouter(LLMService)`: resolve pool → gather candidates from member adapters → eligibility (capabilities + context estimate) → rank (pool order now; hook for registry scores later) → per-pool `asyncio.Semaphore` → attempt loop reusing `FAILURE_POLICIES` + cooldown bookkeeping (in-memory `cooldown_until` per route) → cross-adapter fallback ends at the local adapter → provenance includes `pool`.
4. Better token estimator in `estimator.py` (still deterministic; chars/3.5 for prose + per-message overhead; document choice). `ContextWindowExceeded` behavior unchanged: skip-too-small, explicit failure if nothing fits.
5. Chaos tests with `FakeAdapter`s: remote pool exhausted → local serves (brief TEST 6); 20 concurrent requests respect `max_concurrency` (brief TEST 7 — assert peak concurrency via instrumented fake); cooldown removes a 429ing route from the next selection; per-task pool resolution.

**Exit criteria:** TESTS green; exhaustiveness test (16 tasks → non-empty pool); concurrency + all-remote-fail chaos tests pass; `SingleAdapterLLMService` still exists for tests but `PoolRouter` is what `create_app` wiring will use.
**Docs to update:** docs/ROUTING.md (pool table, ranking, cooldowns), implementation log, status flips.
**Out of scope:** DB persistence of registry/provenance (Phase 6), quality scoring (Phase 11).

---

## Phase 6 — Database ✅ (2026-08-22)

**Goal:** Postgres+pgvector persistence: provenance, model registry, business/persona skeletons.
**Prerequisites:** Phase 2 ✅ (interfaces frozen). Does NOT depend on Phases 4–5: consume `ProvenanceRecord` as given.
**Allowed paths:** `apps/backend/bebshax/db/` (new), `apps/backend/alembic/` (new), `apps/backend/pyproject.toml` (+deps), `apps/backend/tests/db/`, `docker-compose.yml` (only if a fix is needed), docs listed below.

Steps:
1. Dependencies (write the R8 review in the implementation log BEFORE installing): `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `pgvector` (python client), dev: `aiosqlite` (unit tests). LOCK.
2. `bebshax/db/`: async engine/session from `settings.database_url`; declarative models: `llm_requests` (all ProvenanceRecord fields; attempts as JSONB), `model_registry` (id, provider, model_name, enabled, context_window, supports_tools/json/vision, reasoning_level, quality_score, latency_score, health_score, last_checked, cooldown_until), `businesses` (id, name, description, created_at), `personas` (id, business_id FK, name, status, version, generation_model, created_at — full attribute schema arrives in Phase 8).
3. Alembic wired to `BEBSHAX_DATABASE_URL`; initial migration creates tables + `CREATE EXTENSION IF NOT EXISTS vector`.
4. `ProvenanceSink`: an `on_provenance` implementation writing `llm_requests` rows (async-safe: queue + writer task or session-per-record; document choice).
5. Tests: unit tests on aiosqlite for model round-trips + sink (vector/JSONB columns conditionally typed for sqlite); integration tests marked `@pytest.mark.integration` (skipped when `BEBSHAX_TEST_PG=0`/db unreachable) run migrations against the docker pgvector db and verify `vector` extension.

**Exit criteria:** TESTS green without docker; with `docker compose up -d db`: `alembic upgrade head` succeeds and integration tests pass; a completed LLM request writes one `llm_requests` row (test via sink + FakeAdapter).
**Docs to update:** implementation log (incl. R8 reviews), docs/TEAM_SETUP.md (migration command), status flips.
**Out of scope:** registry sync jobs (later), persona attribute schema (Phase 8), memory tables (Phase 9).

---

## Phase 7 — Dataset pipeline ✅ 2026-08-22  (track B)

**Goal:** reproducible, license-checked dataset setup with profiles; no blind bulk downloads.
**Prerequisites:** Phase 1 ✅. Independent of everything else.
**Allowed paths:** `scripts/setup_datasets.py`, `scripts/dataset_manifest.py` (or JSON manifest in `data/metadata/`), `data/DATASETS.md`, `apps/backend/tests/datasets/`, `apps/backend/pyproject.toml` (+deps), docs listed below.

Steps:
1. Dependency (R8 review first): `huggingface_hub` (MIT-ish Apache-2.0, official) — prefer it alone over the heavy `datasets` lib; add `datasets` only if streaming slicing genuinely requires it (document the decision). LOCK.
2. Manifest (checked in, machine-readable): per dataset — name, source URL, HF id, license, size estimate, purpose, profile membership (`minimal` ⊂ `development` ⊂ `evaluation` ⊂ `full`), download method (streaming slice / file subset), preprocessing function, required|optional, sha256 of the processed artifact once known. Start from the audit §7 shortlist: PersonaHub (slice), Synthetic-Persona-Chat, EmpatheticDialogues (slice), Amazon Reviews 2023 (1 category slice), RouterArena, xRouteBench (eval profile), MMLU/GSM8K micro-slices (health probes). Verify each license AT DOWNLOAD TIME; abort a dataset whose license/gating fails and record it in data/DATASETS.md.
3. `python scripts/setup_datasets.py --profile development`: idempotent (checksum check → skip), downloads to `data/raw/`, preprocesses to `data/processed/` (normalized JSONL), writes per-dataset metadata to `data/metadata/`, prints a summary table, non-zero exit on required-dataset failure. `--verify-only` mode.
4. `data/DATASETS.md` generated/updated from the manifest (single source: manifest).
5. Tests (no network): manifest schema validation; profile subset relation; idempotence + checksum logic with tiny local fixture files; preprocessing functions on fixture samples.

**Exit criteria:** TESTS green offline; live run of `--profile minimal` completes on the dev machine; re-run is a no-op; `data/DATASETS.md` lists every manifest entry with license + purpose; total minimal profile < 1 GB, development < 5 GB.
**Docs to update:** data/DATASETS.md, implementation log (R8 review), docs/TEAM_SETUP.md (one-command line), status flips.
**Out of scope:** embeddings/evidence indexing (Phases 8–9), any training.

---

## Phase 8 — Persona engine ⬜  (track A after Phase 5; needs 6 for storage, 7 for evidence seeds)

**Goal:** generate validated, evidence-grounded, stored personas.
**Allowed paths:** `apps/backend/bebshax/persona/` (new), `apps/backend/bebshax/api/personas.py`, `apps/backend/tests/persona/`, alembic revision for persona attribute/evidence tables, docs listed below.

Steps:
1. Pydantic + DB schema per brief §14: identity fields, goals/pain_points/needs/motivations/behaviors/constraints/…, each attribute carrying provenance class `OBSERVED | INFERRED | SYNTHETIC` + optional evidence links; `Evidence` objects (§17: id, source, text, type, timestamp, relevance, confidence, persona_id).
2. Pipeline: business description → evidence retrieval from processed datasets → persona spec → `TaskType.PERSONA_GENERATION` (json_mode) via `LLMService` → parse/validate (pydantic; `MALFORMED_RESPONSE` retry is infra, schema-invalid-after-parse goes to refinement ONCE via `PERSONA_REFINEMENT`) → deterministic consistency rules (age/occupation, income/behavior, location/timezone — table-driven) → optional `CRITIC` pass → store with version=1.
3. REST: `POST /api/businesses`, `POST /api/businesses/{id}/personas` (generate), `GET /api/personas/{id}`.
4. Tests: schema round-trip; pipeline with `FakeAdapter` scripted JSON (valid, invalid-then-refined, contradiction-flagged); consistency rules unit-tested with the brief §18 examples; API happy-path via TestClient.

**Exit criteria:** TESTS green; with live routing + db up: one real persona generated end-to-end and visible via GET; every stored attribute has a provenance class.
**Docs to update:** docs/PERSONA_ENGINE.md (new), implementation log, status flips.

---

## Phase 9 — Memory ⬜  (track B after Phase 6; consumes Phase 8 persona ids)

**Goal:** persistent persona memory: pgvector stream with relevance+recency+importance retrieval and reflection.
**Allowed paths:** `apps/backend/bebshax/memory/` (new), alembic revision (memory tables + vector column/index), `apps/backend/tests/memory/`, docs listed below.

Steps:
1. Embeddings via freellmpool's embedding failover (`pool.embed`) exposed through a new `EmbeddingService` + adapter method (R1: implementation inside `adapters/`); deterministic local fallback (hash-based) for offline tests.
2. Tables: `memory_items` (persona_id, kind: semantic|episodic|reflection, text, embedding vector, importance float, created_at, last_accessed); write path (observations from conversations), retrieval score = w_rel·cosine + w_rec·exp-decay + w_imp·importance (weights in config; document defaults); reflection job summarizing clusters of episodic items into semantic/reflection items via `MEMORY_SUMMARIZATION`.
3. Tests: scoring math (deterministic vectors), retrieval ordering, reflection with `FakeAdapter`, sqlite-safe unit path + pg integration marker (same pattern as Phase 6).

**Exit criteria:** TESTS green; integration: store 20 memories → query returns the expected top-k ordering; reflection produces a stored summary item.
**Docs to update:** docs/PERSONA_ENGINE.md (memory section), implementation log, status flips.

---

## Phase 10 — Interview engine ⬜  (track A after 8; uses 9)

**Goal:** multi-turn interviews with stable persona identity.
**Allowed paths:** `apps/backend/bebshax/interview/` (new), `apps/backend/bebshax/api/interviews.py`, conversation tables migration, `apps/backend/tests/interview/`, docs listed below.

Steps:
1. Conversation model (id, persona_id, objective, status, turns). Per-turn composition (never regenerate the persona): system = persona identity card + constraints; context = retrieved memories (Phase 9) + relevant evidence + business context + objective; history = prior turns (full — if the estimator says nothing fits, that is `ContextWindowExceeded`, not truncation of identity/evidence; older small-talk turns may be summarized ONLY via `MEMORY_SUMMARIZATION` with the summary stored as memory, never silently dropped).
2. `TaskType.PERSONA_INTERVIEW` → conversation pool; write each turn as observation memories; REST: create conversation, post interviewer message → persona reply (non-streaming now; streaming later), get transcript.
3. Tests: composition snapshot (identity always present), multi-turn stability with scripted `FakeAdapter`, memory write-back, API flow.

**Exit criteria:** TESTS green; live: 5-turn interview keeps name/age/occupation consistent (assert via transcript check script or eval hook).
**Docs to update:** docs/PERSONA_ENGINE.md (interview section), implementation log, status flips.

---

## Phase 11 — Quality & evaluation ✅ (2026-08-22, track C)

**Goal:** measure persona quality and routing strategies; answer the research question.
**Allowed paths:** `apps/backend/bebshax/evaluation/` (new), `scripts/run_evaluation.py`, `apps/backend/tests/evaluation/`, docs listed below.

Steps:
1. Persona metrics: validity (schema+provenance completeness), consistency (deterministic rules + contradiction scan across turns via `CONTRADICTION_CHECK`), grounding ratio (evidence-linked attributes / total). Reports as JSON + markdown.
2. Routing strategies behind config: ROUND_ROBIN / LEAST_USED / QUALITY_FIRST / LATENCY_FIRST / CAPABILITY_FIRST / QUOTA_AWARE / HYBRID (default). Implement as pluggable rankers in the Phase-5 router; chaos-sim comparison harness (FakeAdapters with scripted latency/failure distributions) → table: success rate, fallback count, latency, context failures per strategy.
3. Offline routing eval vs literature: RouterArena/xRouteBench replay data (eval profile from Phase 7) — comparison numbers only, never in the request path.
4. `python scripts/run_evaluation.py --suite personas|routing|all` produces `data/metadata/eval_report_<date>.md`.

**Exit criteria:** TESTS green; one command yields the naive-vs-intelligent routing table + persona quality report (brief §29).
**Docs to update:** docs/EVALUATION.md (new), implementation log, status flips.

---

## Phase 12 — Frontend ✅ (2026-08-22 — Foundation + mock layer complete, track C)

**Goal:** the single React+Vite app.
**Prerequisites:** Phase 1 ✅ only. Backend endpoints are mocked until they exist — `VITE_MOCK=1` mode with fixtures mirroring the pydantic models (`ProvenanceRecord`, persona schema).
**Allowed paths:** `apps/frontend/**` ONLY, plus docs listed below. Never touch `apps/backend`.

Steps:
1. Scaffold: Vite + React + TypeScript in `apps/frontend`; router; API client with `VITE_API_BASE` (default `http://127.0.0.1:8000/api`) and a mock layer (fixtures in `apps/frontend/src/mocks/`) toggled by `VITE_MOCK`.
2. Views (build in this order): 1) Routing dashboard: request list → expandable candidates/failures/served_by/latency/tokens (shape = `ProvenanceRecord`); provider status; fallback history. 2) Business setup (create/list). 3) Persona generation + profile (attributes grouped, provenance badges OBSERVED/INFERRED/SYNTHETIC, evidence links). 4) Persona memory view. 5) Interview chat. 6) Insights/eval metrics.
3. First task (do before coding): write `docs/API_CONTRACT.md` from the existing pydantic models + planned endpoints in this file; backend phases must keep it updated when they land endpoints (contract-first).
4. Testing: `vitest` component tests for the routing dashboard + persona profile with mock fixtures; `npm run build` must pass.

**Exit criteria:** `npm run build` + `npm test` green in `apps/frontend`; app fully navigable with `VITE_MOCK=1`; health view shows live `/api/health` when backend runs.
**Docs to update:** docs/API_CONTRACT.md (new), docs/TEAM_SETUP.md (frontend commands), implementation log, status flips.

---

## Phase 13 — Integration + demo mode ⬜  (all tracks converge)

**Goal:** end-to-end flows wired; exhibition-safe demo mode.
**Allowed paths:** whole repo (coordinated).
Steps: wire frontend to real endpoints (mock mode stays); `BEBSHAX_DEMO_MODE=true` → seed cached known-good personas/interviews, clearly labeled "cached" in UI and API responses, live generation still available; offline drill: remote providers disabled → Ollama + cache keep the demo alive.
**Exit criteria:** demo walkthrough script (`docs/DEMO.md`) executes with network unplugged; TESTS green; frontend build green.
**Docs to update:** docs/DEMO.md (new), implementation log, status flips.

## Phase 14 — Testing hardening ⬜  (all)

Full matrix from the brief §37/§44: provider down / 429 / timeout / context overflow / model gone / whole chain / all-fail→Ollama / structured-output failure / persona consistency / dataset loading / provenance / caching / 20-concurrent generation. Map each of the 10 acceptance tests to a named test; add missing ones; fix what they expose. **Exit:** every §44 test passes or has a documented, owner-approved deviation.
**Docs to update:** implementation log (acceptance-test table), status flips.

## Phase 15 — Documentation ⬜  (all)

README polish, docs/{ARCHITECTURE, FAILOVER, MODEL_REGISTRY, SETUP}.md, FINAL_IMPLEMENTATION_REPORT.md (what was built, OSS used + versions + licenses, datasets + licenses, routing/fallback architecture, limitations, security, performance + eval results, future work), one-shot `scripts/setup.py`. **Exit:** fresh-machine setup succeeds following SETUP.md alone.
**Docs to update:** everything above, final status flips.
