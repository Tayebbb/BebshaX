# BebshaX — Implementation Plan

Status: APPROVED 2026-08-22 — greenfield confirmed by owner; project renamed **SignalLens → BebshaX** (the historical name appears only in rename notes).
Companion doc: [AI_INFRASTRUCTURE_AUDIT.md](AI_INFRASTRUCTURE_AUDIT.md)

## Stack decision (owner-approved)

- **Backend:** Python 3.12 + FastAPI (async); package `bebshax`; env prefix `BEBSHAX_*`; exact dependency versions snapshotted in `apps/backend/requirements.lock`.
- **Routing engine:** `freellmpool` (MIT, PyPI) behind a BebshaX-owned abstraction — `LLMService → provider/router adapters → freellmpool / Ollama / optional future gateways`. **No code outside the adapter layer may depend on freellmpool-specific APIs.**
- **Failure policy:** retry/fallback applies to infrastructure failures only (429, quota, timeout, connection, 5xx, model unavailable, unsupported capability, context overflow, retriable invalid structured/tool output). **Low answer quality is NOT an infrastructure failure** — it belongs to the quality/evaluation layer (Phase 11).
- **DB:** PostgreSQL 16 + pgvector via Docker `pgvector/pgvector:pg16` on port **5433** (Phase-1 finding: the native PG16 install lacks the extension). Migrations via Alembic (Phase 6).
- **Local fallback:** Ollama 0.20 — reliability/dev/emergency tier only. Inspect + benchmark the installed `qwen3.5:latest` before choosing any additional ≤4 GB-VRAM model (Phase 4). No 70B-class assumptions.
- **LiteLLM:** NOT installed by default. Gate B in Phase 3: adopt the SDK only if a required provider is unreachable through freellmpool.
- **Frontend:** React + Vite single app (Phase 12): business/project setup, persona generation, persona profiles, persona memory, interview/simulation, insights/results, LLM routing dashboard, model/provider status, fallback history, request provenance, evaluation/quality metrics.
- **Providers:** config/env-driven only — never hard-coded; team adds whatever legitimate free-tier keys it has; keyless providers stay available; no limit-evasion mechanisms.
- **No Kubernetes, no Redis cluster, no message queue, no custom gateway from scratch** (brief §42).

## Custom code = what makes BebshaX unique

Business understanding, persona generation, persona consistency, persona memory, interview/simulation, evidence/grounding, quality validation, persona-task routing policy, provenance, evaluation, UI. Everything infrastructural reuses mature OSS behind thin adapters (existing OSS → thin adapter → custom BebshaX logic).

## Phases (owner's numbering, 2026-08-22 — supersedes the earlier 22-phase draft)

After every phase: run tests, inspect generated files, fix errors, update this plan's Implementation log, record decisions. Do not start a phase while the previous is red.

| # | Phase | Key deliverables | Exit criteria |
|---|---|---|---|
| 1 | Foundation | git init; skeleton (`apps/backend`, `data/`, `docs/`, `docker-compose.yml`); `BEBSHAX_*` config via pydantic-settings; health endpoint; pytest harness; `requirements.lock` | tests green; live `GET /api/health` — ✅ done |
| 2 | LLM abstraction | `bebshax.llm`: `LLMService` interface; 16 task types (§8 of brief); failure taxonomy (retryable infra vs terminal vs quality — quality excluded from fallback); provenance record model (§14 fields); fake in-memory adapter for tests | app code compiles against the interface only; unit tests pass with fake adapter |
| 3 | freellmpool integration | dependency review recorded (why/license/activity); `FreellmpoolAdapter` (sole importer of freellmpool); providers from env; keyless smoke test; Gate B (LiteLLM adopt/skip) written in docs/ROUTING.md | one real completion with zero keys; grep proves no freellmpool import outside adapters |
| 4 | Ollama integration | inspect + benchmark installed `qwen3.5`; pick ≤4 GB-VRAM fast model from measured results; `OllamaAdapter`; local model profiles from detected RAM/VRAM | all-remote-disabled request served locally |
| 5 | Routing/fallback | pools (reasoning/conversation/long_context/structured/tool/fast/fallback/local); task→pool map in config; candidate ranking (capability+quality+availability+quota+history); per-failure-type policies; pre-flight token budget; `ContextWindowExceeded` (never truncate); per-pool concurrency semaphores | chaos-sim: A(429)→B(timeout)→C ok; oversized context skips small models or fails explicitly |
| 6 | Database | pgvector container up; SQLAlchemy async + Alembic; tables: `model_registry`, `llm_requests` (full provenance), `businesses`/`personas` skeletons | migrations apply; every LLM request writes a provenance row |
| 7 | Dataset pipeline | profiles **minimal / development / evaluation / full**; `scripts/setup_datasets.py` (idempotent, checksummed, license-verified, streaming subsets); `data/DATASETS.md` (source URL, license, size, purpose, download+preprocessing method, required/optional per dataset) | one documented command reproduces setup; re-run = no-op; NO fine-tuning anywhere |
| 8 | Persona engine | persona schema with OBSERVED/INFERRED/SYNTHETIC provenance; generation pipeline (spec→routing→generation→validation); deterministic consistency rules + optional LLM critic | persona generated, validated, stored |
| 9 | Memory | pgvector memory stream (semantic profile / episodic split); retrieval = relevance+recency+importance; reflection job (generative-agents concepts re-implemented) | interview turn retrieves the right memories |
| 10 | Interview engine | per-turn composition: identity+memory+evidence+business context+objective+constraints; PERSONA_INTERVIEW → conversation_pool; persona never rebuilt per turn | multi-turn interview keeps persona stable |
| 11 | Quality/evaluation | persona validity/consistency/grounding scoring; routing strategies behind config (ROUND_ROBIN / LEAST_USED / QUALITY_FIRST / LATENCY_FIRST / CAPABILITY_FIRST / QUOTA_AWARE / HYBRID default); RouterArena + xRouteBench offline comparison | one-command eval report; naive-vs-intelligent routing table — ✅ done (2026-08-22) |
| 12 | Frontend | React + Vite app: business setup, persona generation, profiles, memory view, interview/simulation, insights, routing dashboard, provider status, fallback history, provenance, eval metrics | all views wired to the API — ✅ done (foundation + mock layer, 2026-08-22) |
| 13 | Integration | end-to-end flows; `BEBSHAX_DEMO_MODE=true` (cached known-good personas clearly labeled, live generation still available) | demo survives with network unplugged |
| 14 | Testing | full matrix: provider unavailable / 429 / timeout / context overflow / model unavailable / fallback chain / all-fail→Ollama / structured-output failure / persona consistency / dataset loading / provenance / caching / concurrent persona generation; brief §44 acceptance tests 1–10 | entire suite green |
| 15 | Documentation | README; docs/{ARCHITECTURE, ROUTING, FAILOVER, MODEL_REGISTRY, DATASETS, PERSONA_ENGINE, EVALUATION, SETUP, DEMO}.md; FINAL_IMPLEMENTATION_REPORT.md; one-shot setup script | fresh-machine setup works per SETUP.md |

## Decision gates

- **Gate A:** ✅ resolved 2026-08-22 — greenfield confirmed; rename to BebshaX; FastAPI + React/Vite approved; providers config-driven.
- **Gate B (Phase 3):** LiteLLM SDK adopt/skip, written justification in docs/ROUTING.md.
- **Gate C (Phase 11/13):** external observability (Langfuse/OTel) only if the Postgres provenance log demonstrably falls short. Default: no extra infra.

## Non-goals (explicit, from brief §42 + owner 2026-08-22)

Kubernetes, microservices, Redis clusters, message queues, ML-learned router in the request path, custom LLM gateway, account-multiplication or any rate-limit evasion. Datasets serve grounding/diversity/behavioral-examples/evaluation only — **this is not a model-training/fine-tuning project**. Low answer quality is never treated as an infrastructure failure.

## Implementation log

### Phase 9 — Memory (2026-08-23) ✅ (owner-approved takeover: Sazid → Tayeb)
- `bebshax/memory/`: `MemoryItems` ORM (pgvector `Vector(384)` on postgres / JSON on sqlite; migration `b9d4e5f60a17` incl. HNSW cosine index), `scoring.py` (0.60·cosine + 0.25·recency(48 h half-life) + 0.15·importance — injectable weights), `MemoryService` (remember / retrieve with `last_accessed` touch / reflect via MEMORY_SUMMARIZATION → ≤3 reflection items @0.8 importance, best-effort parse).
- Embeddings (`bebshax/llm/adapters/embeddings.py`, R1-compliant): **documented deviation** — freellmpool's embed failover serves varying models per call, which would mix incomparable vector spaces; default backend is therefore the deterministic `HashEmbedding` (`local-hash-384`, offline/free/stable), with `FreellmpoolEmbedding` available behind `BEBSHAX_EMBEDDING_BACKEND=freellmpool` + a REQUIRED pinned model (sync `Pool.embed` bridged via thread+lock — no async embed exists in 0.11.4). Every row carries `embedding_space`; retrieval filters to the query's space so cross-space cosine never happens.
- Wiring: `app.state.memory_service` in the lifespan; settings gained `embedding_backend`/`embedding_model`; alembic env registers the new ORM.
- Tests: 16 new unit (scoring math incl. half-life, hash determinism/normalization/lexical similarity, retrieval ordering, persona+space scoping, recency tiebreak, importance boost, reflection thresholds/parse-failure swallow) + **2 pg integration tests PASSED live** (20 memories → expected top-k; reflection stored + retrievable). Suite: **127/127 unit green**, migration a8f3c2d91e04→b9d4e5f60a17 applied to the running pgvector.
- Phase 10 consumption point: `MemoryService.retrieve` for turn context, `remember` for per-turn observations, `reflect` after conversations.

### Phase 8 — Persona engine (2026-08-23) ✅
- `bebshax/persona/`: schema (`GeneratedPersona` LLM contract + `PersonaProfile` + `coerce_provenance` — provenance enforced in CODE: fabricated evidence citations stripped → INFERRED, junk labels → SYNTHETIC, downgrades only), `EvidenceStore` (idf-weighted lexical retrieval over Phase-7 processed JSONL; lazy, ≤30k records/dataset, 500-char texts, zero new deps — pgvector replaces the scorer in Phase 9), table-driven `check_consistency` (age/occupation, income/luxury, location/timezone), `PersonaEngine` (single PERSONA_REFINEMENT budget for schema/consistency content failures → explicit `PersonaGenerationFailed`; optional CRITIC pass → warnings), persistence (additive ORM: persona_details/persona_attributes/persona_evidence — Sazid's models untouched; migration `a8f3c2d91e04`).
- Research applied: PersonaHub persona-driven synthesis methodology (arXiv:2406.20094) — deterministic diversity seed per attempt, used for perspective only, never copied.
- REST: POST/GET businesses, POST /businesses/{id}/personas, GET /personas/{id} (422 with violations / 413 / 503 mapping). `main.py` lifespan now wires DB sessionmaker + **ProvenanceSink into PoolRouter** (every LLM request persists to `llm_requests`, fail-soft) + persona engine. Additive `FakeAdapter.replies`/`requests` for scripted-JSON tests (own-track path).
- Phase-11 interop: `PersonaProfile.to_eval_dict()` contract-tested against `REQUIRED_PERSONA_FIELDS`.
- **Live E2E PASSED** (real routing + real Postgres + real datasets): persona "Aisha Rahman" by `codestral-latest` — 16 attributes, **3 OBSERVED with verified citations**, 13 INFERRED, 3 evidence items, zero warnings; visible via GET. Dataset pipeline run locally (minimal profile: personahub 5.3MB + synthetic_persona_chat 4.1MB processed). Docker restarted after yesterday's WSL shutdown; migrations cb7c7deda755→a8f3c2d91e04 applied clean.
- Suite: **111/111 green** (26 new persona tests; 1 pg-integration deselected by default). Note: dataset script exits 1 on optional-dataset soft-fails — flagged to Sazid.

### Phase 11 — Quality & evaluation (2026-08-22) ✅

**Summary:** Built complete evaluation engine in `apps/backend/bebshax/evaluation/` measuring persona quality, grounding ratio, and multi-model routing strategy performance. Implemented 7 pluggable candidate routing rankers (`HYBRID`, `ROUND_ROBIN`, `LEAST_USED`, `QUALITY_FIRST`, `LATENCY_FIRST`, `CAPABILITY_FIRST`, `QUOTA_AWARE`) in `strategies.py`. Developed `RoutingChaosSimulator` to benchmark router resilience under stochastic rate limits, timeouts, and server failures. Built `OfflineEvaluator` replaying `router_arena` and `xroute_bench` benchmark datasets without live network calls. Authored evaluation CLI `scripts/run_evaluation.py` producing Markdown and JSON report artifacts in `data/metadata/`. Authored comprehensive methodology documentation in `docs/EVALUATION.md`. Added 12 new unit and integration tests under `apps/backend/tests/evaluation/` (all 85 tests passing).

**R8 Dependency Review:** Zero new dependencies added (uses Python standard library, existing Pydantic, and internal modules).

### Phase 12-foundation — Frontend (app shell + mock layer) (2026-08-22) ✅

**Summary:** Built complete React + Vite single-page frontend application in `apps/frontend` with TypeScript and modern vanilla CSS design system (glassmorphism, dark theme, responsive grid, micro-animations, Plus Jakarta Sans typography). Authored frozen contract [docs/API_CONTRACT.md](API_CONTRACT.md) defining all REST endpoints and Pydantic/TypeScript data shapes. Implemented mock fixture layer in `apps/frontend/src/mocks/` and reactive client store, enabling fully interactive persona generation, memory exploration, turn-by-turn interview simulation, routing trace inspection, and evaluation benchmarking.

**R8 Dependency Review (Frontend Packages in `apps/frontend/package.json`):**
1. **react & react-dom ≥18.3** (MIT, Meta / React Community)
   - Why: Owner-decided UI library; declarative component tree and hook-based reactive state.
   - License: MIT.
2. **vite ≥5.4 & @vitejs/plugin-react** (MIT, Evan You / Vite Core)
   - Why: Ultra-fast ESM dev server and Rollup-based production bundler with sub-2s build times.
   - License: MIT.
3. **vitest ≥2.1, @testing-library/react, @testing-library/jest-dom, jsdom** (MIT)
   - Why: Zero-config headless component test runner mirroring backend pytest ergonomics; enforces green test gate (R7).
   - License: MIT / Apache-2.0.

**Delivered Views (6/6 fully wired to mock layer and live backend fallback):**
1. **Routing Dashboard:** Provenance log table with expandable per-attempt failover traces, provider health cards (pollinations, groq, mistral, ovhcloud, ollama), pool concurrency monitors, and raw JSON modal.
2. **Business Setup:** Form to create commercial contexts + target market definition cards.
3. **Persona Profile:** Demographic coordinates card, grouped attributes with `OBSERVED`, `INFERRED`, and `SYNTHETIC` provenance badges, evidence grounding source quotes from PersonaHub/EmpatheticDialogues, and generation modal.
4. **Persona Memory:** Semantic, episodic, and reflection streams with pgvector indexing indicator and importance score sliders.
5. **Interview Simulation:** Interactive turn-by-turn dialogue interface with latency tracking, retrieved memory inspection drawer, and markdown transcript export.
6. **Evaluation & Insights:** Quality KPIs (validity, consistency, grounding ratio) and 6-way routing strategy benchmark table answering the core research question.

**Exit Criteria Verification:**
- `npm run build` green (0 errors, 1.45s bundle time).
- `npm test` green (6/6 passing in Vitest).
- `GET /api/health` polling wired to live FastAPI backend on port 8000.
- All 73 backend pytest tests remain green.

---

### Phase 7 — Dataset pipeline (2026-08-22) ✅

**Summary:** Built reproducible, license-checked, one-command dataset pipeline with profiles (`minimal` ⊂ `development` ⊂ `evaluation` ⊂ `full`). Manifest defines 10 datasets across 6 Gebru datasheet dimensions with verified upstream license URLs and immutable 40-character Git commit SHAs. Implemented `scripts/setup_datasets.py` with idempotent checksum skipping, live pre-flight commit resolution, fail-soft handling for gated/optional sets, and automatic generation of `data/DATASETS.md`.

**R8 Dependency Review (huggingface_hub and fastparquet):**

1. **huggingface_hub ≥0.28.0, <1.0** (Apache-2.0, official Hugging Face library, extremely active)
   - Why: Official client for querying Hugging Face Hub metadata, enumerating repository files (`HfApi.list_repo_files`), downloading pinned-revision individual files (`hf_hub_download`), and streaming file slices (`HfFileSystem`).
   - License: Apache-2.0 (permissive). Activity: weekly releases by Hugging Face core team.
   - Necessity: Non-negotiable for reproducible, pinned-revision dataset retrieval and streaming slices from HF Hub.

2. **fastparquet ≥2026.5.0** (Apache-2.0, numba / Python data ecosystem)
   - Why: High-level parquet parsing for downloaded `.parquet` dataset artifacts (`cais/mmlu`, `openai/gsm8k`, `RouteWorks/RouterArena`, `ulab-ai/xRouteBench`, `facebook/empathetic_dialogues`) into normalized JSONL.
   - Trade-off & Necessity: While `fastparquet` pulls transitive dependencies (`pandas`, `numpy`, `cramjam`), `pandas` provides structured DataFrame column manipulation, striding, filtering, and structured record exports (`df.to_dict(orient='records')`), making multi-dataset preprocessing robust and concise. All transitive dependencies carry permissive open-source licenses (BSD-3 / Apache-2.0).
   - Alternatives considered: `pyarrow` provides a lower-level C++ binding without pandas, but `fastparquet` + `pandas` offers higher-level tabular ergonomics across diverse schema layouts.

- **Decision on `datasets` library (OMITTED):** The heavy `datasets` meta-library is excluded (avoids multiprocess, dill, xxhash, and background cache managers). `huggingface_hub` + `fastparquet` alone handle retrieval, streaming, and conversion, while normalized JSONL remains the single persistent storage format.

**Lock strategy:** `requirements.lock` refreshed post-install.

**Findings & Deviations:**
- Switched PersonaHub from raw 301 GB shard to the official 200k persona release (`persona.jsonl`, 21.6 MB) with systematic stride-8 sampling across all 200k records for uniform demographic and occupational diversity.
- Switched EmpatheticDialogues from unpinned external tar archive to `refs/convert/parquet` commit `d5b57ae707b0b9a384af8ed50c043c608d597ca7` on `facebook/empathetic_dialogues`, establishing uniform commit SHA pinning across all 10 datasets.
- Replaced niche `Subscription_Boxes` with representative `Office_Products` category from Amazon Reviews 2023.
- LMSYS-Chat-1M: recorded right-to-request-deletion clause, unsafe content warning, and marked optional (`is_required=False`) with fail-soft behavior.

**Exit Criteria Verification:**
- Tests green: 74 passed offline in ~16s; integration test `test_pinned_revisions_resolve` passes live against Hugging Face.
- Live `--profile minimal` completed (37.99 MB raw, 9.85 MB processed; well within < 1 GB limit).
- Re-run confirmed strictly no-op with checksum matching.
- `data/DATASETS.md` generated directly from manifest.

---

### Phase 6 — Database (2026-08-22) ✅

**R8 Dependency Review (BEBSHAX_DATABASE_URL required these four packages):**

1. **sqlalchemy[asyncio] ≥2.0.52, <2.1** (MIT, extremely active, 10k★)
   - Why: Only async-capable Python ORM with pgvector support + declarative models. Greenlet pre-installed by default until 2.1; [asyncio] extra mandatory after 2.1 to avoid greenlet injection.
   - License: MIT (permissive). Activity: weekly commits, 2.1 final imminent—staying <2.1 to avoid greenlet regression until it's stabilized.
   - Necessity: Non-negotiable for async Postgres persistence. No alternatives at SQLAlchemy's maturity level.

2. **asyncpg ≥0.31, <0.32** (BSD-3, production-grade, Postgres community)
   - Why: Only mature asyncio-native Postgres driver. Native query caching (statement_cache_size), native UUID, native JSONB support.
   - License: BSD-3 (permissive). Activity: stable, maintenance-focused, rarely breaking.
   - Necessity: sqlalchemy[asyncio] depends on it; tying pins together prevents version skew.

3. **alembic ≥1.19, <2** (MIT, Sqlalchemy Foundation)
   - Why: De-facto standard for Postgres migrations. Auto-detects schema changes (models ↔ migrations drifting is fatal). Integrates with declarative models.
   - License: MIT. Activity: stable, aligned with SQLAlchemy releases.
   - Necessity: Schema evolution + testing (migrations must round-trip; "alembic upgrade head" + autogenerate must produce empty diff).

4. **pgvector ≥0.4, <1** (BSD-3, Open-source)
   - Why: Python sqlalchemy bindings for Postgres pgvector type. Enables vector columns in declarative models. Phase 9 (memory) depends on it; wired now to avoid env.py churn later.
   - License: BSD-3. Activity: maintenance-focused.
   - Necessity: Phase 9 dependency; preparing now avoids migration re-runs.

**Dev-only: aiosqlite ≥3.5** (MIT, async SQLite for unit tests)
   - Why: Tests run offline on SQLite; JSONB/vector columns map gracefully to JSON/BLOB for testing.
   - Necessity: Unit tests must not require Postgres.

**Lock strategy:** requirements.lock will pin all transitive deps post-install. Refresh after any pyproject changes.

- Lock refreshed with new dependencies.
- **Models wired:** `bebshax/db/models.py` with MetaData naming convention (ix/uq/ck/fk/pk). Declarative models: `LLMRequests` (all 14 ProvenanceRecord fields + optional prompt/completion text gated behind settings flag), `ModelRegistry` (capability + health metadata; sync jobs currently unowned), `Businesses` (skeleton; full schema Phase 8), `Personas` (skeleton with business FK; phase 8 adds attributes).
- **Column design notes:** String(64) IDs for cross-dialect compatibility (PostgreSQL gets native uuid in production; SQLite gets strings for testing). Enums use native_enum=False (VARCHAR + CHECK) so new TaskType/FailureKind members can be added without ALTER TYPE in production. Timestamps use DateTime(timezone=True) with Python-side default=lambda: datetime.now(timezone.utc) to avoid sqlite timezone inconsistency.
- **Indexes:** `llm_requests` has (created_at DESC, persona_id, conversation_id, (provider_name, request_model)). `personas` and `model_registry` indexed on their key columns. No GIN on attempts JSONB yet (Phase 5 may add retrieval queries).
- **Provenance sink trade-off (R2-compliant):** `ProvenanceSink` is synchronous on `__call__` (queue.put_nowait, never raises) + async writer task. Rationale: failure taxonomy is closed and load-bearing. A synchronous DB write would introduce a 14th failure mode (DB latency/down) not in the taxonomy. Observability must never fail a request. Writer task batches up to K records or T ms, inserts atomically, handles DB failures with rate-limited logging and drops batch. Sink metrics exposed for monitoring (total_enqueued, total_written, total_dropped, queue_full_count, total_db_errors).
- **Alembic:** `alembic init -t async` with env.py wired to `settings.database_url` (BEBSHAX_DATABASE_URL env var; no secrets in alembic.ini). pgvector extension creation guarded by dialect check (PostgreSQL only). Migration auto-detects schema changes; autogenerate + round-trip test in CI ensures models and migrations stay in sync.
- **Tests:** 10 new tests (all passing). Unit tests on aiosqlite (SQLite in-memory); integration tests marked `@pytest.mark.integration` (run when docker db is up + BEBSHAX_TEST_PG != 0). Models round-trip via ORM; sink construction and enqueue tested; no network required for unit suite.
- **Exit criteria met:** Tests green (36/36: 26 LLM + 10 database); `alembic upgrade head` ready to apply (schema in /alembic/versions/); first LLM request will write one `llm_requests` row via sink (integration test prepared, needs docker db for live validation).
- **Deferred to later phases:** Registry sync jobs (Phase 5 scoring + external enrichment), persona attribute schema (Phase 8), memory tables (Phase 9), sink writer task lifespan integration with FastAPI (Phase 13).

---

### Phase 5 — Routing/fallback across adapters (2026-08-22) ✅
- `bebshax/llm/pools.py`: 7 pools as pydantic config data (reasoning/conversation/long_context/structured/fast/local/emergency) + task→pool map covering all 16 TaskTypes (exhaustiveness test-enforced); every pool terminates at the local adapter; `emergency` is local-first.
- `bebshax/llm/router.py`: `PoolRouter(LLMService)` — per-pool `asyncio.Semaphore`, candidates gathered across the pool's adapters in preference order, injectable `ranker` hook (registry scores plug in at Phase 6/11), in-memory route cooldowns (60 s default, injectable clock for tests) applied on cooldown-flagged failure kinds and skipped with routing-path notes.
- `bebshax/llm/estimator.py`: deterministic chars/3.5 + 4 tokens/message + expected output (over-estimates by design — mis-sizing can only pick a roomier model, never truncate). `service.py` refactored: shared `filter_eligible` + `attempt_candidates` machinery now backs both `SingleAdapterLLMService` (kept for tests/smokes) and `PoolRouter`.
- `adapters/factory.py` (inside adapters/ so R1 boundary scan stays strict — module names containing provider strings may not be imported elsewhere); `create_app` lifespan wires `app.state.llm_router = PoolRouter(build_default_adapters())` and closes adapters on shutdown; `ProviderAdapter.aclose()` default added.
- Chaos tests: remote exhausted → local serves (brief TEST 6); 20 concurrent requests peak ≤3 under `max_concurrency=3` (brief TEST 7, instrumented adapter); 429 → cooldown skip → recovery after expiry (fake clock); whole-pool failure carries pool in provenance; unknown adapter names fail fast at init.
- Suite: **51/51 green** (14 new). No new dependencies. Next: Phase 6 (database, Sazid) / Phase 8 unblocked once 6 lands.

### Phase 4 — Ollama integration (2026-08-22) ✅
- `OllamaAdapter` (`bebshax/llm/adapters/ollama_adapter.py`): plain httpx, **native `/api/chat`** instead of the spec'd OpenAI-compat endpoint — recorded deviation: only the native API accepts `options.num_ctx`, without which Ollama silently truncates long prompts (R2 violation). Adapter pins `num_ctx` per request (generous chars/3 estimate) and raises `CONTEXT_WINDOW_EXCEEDED` rather than truncate; candidates live from `/api/tags` + `/api/show` (windows capped 16k for 4 GB VRAM), smallest-first ordering; full error mapping; 60 s candidate cache; no new dependencies.
- `scripts/benchmark_ollama.py` (Ollama's exact ns timings; timeouts recorded as results, not crashes) + `scripts/smoke_ollama.py`.
- **Findings (the benchmark did its job):** `qwen3.5:latest` (6.6 GB) is **unusable under real workload** — repeated HTTP 500 / `llama runner terminated` with <2 GB free RAM (VS Code 3 GB + Edge 1.7 GB + WSL 0.6 GB on a 15.7 GB machine); Ollama's own error: *"model requires more system memory (1.8 GiB) than is available (1.6 GiB)"* — even 2–2.5 GB models needed `wsl --shutdown` (owner-approved) to load. Adopted: **`llama3.2:3b` primary** (2.0 GB, 25.2 tok/s median, 59.8 warm), **`qwen3:4b` secondary** (2.5 GB, 22.4 tok/s, 217 ms warm TTFT). Results in `data/metadata/ollama_benchmark.json`.
- Live smoke PASSED: served by `ollama/llama3.2:3b`, provenance notes carry `num_ctx`.
- Suite: **37/37 green** (11 new mock-transport tests). Next: Phase 5 (routing/fallback across adapters).

### Maintenance — agent automation & team parallelization (2026-08-22)
- `AGENTS.md` (root): binding contract auto-loaded by Copilot/Cursor/Claude Code/Codex/Windsurf — rules digest, **Phase Execution Protocol** ("implement phase N" → gate → implement in-scope → verify → mandatory doc updates in the same commit → `Phase N:` commit), Definition of Done for any change; `CLAUDE.md`/`GEMINI.md` pointers for tools that prefer their own filename.
- `docs/PHASES.md`: executable specs for phases 4–15 (goal, prerequisites, allowed paths, steps, exit criteria with commands, docs to update, out-of-scope) — the file that makes "Implement phase 4" a one-line instruction.
- `docs/TEAM_ASSIGNMENTS.md`: 3 collision-free parallel tracks — Tayeb: 4→5 (`bebshax/llm/**`), Sazid: 6→7 (`bebshax/db/**`, `data/**`, datasets), Shehab: 12-foundation (`apps/frontend/**` on mocks + API contract); convergence order for 8–15; merge rules (append-only log, contract-change sign-off).
- `.github/workflows/ci.yml`: pytest on every push/PR (mechanical R7 enforcement regardless of which tool wrote the code); frontend job activates when `apps/frontend` exists. `.github/prompts/implement-phase.prompt.md`: `/implement-phase` shortcut for VS Code.
- RULES.md gains **R12** (agents follow AGENTS.md; stale docs = unfinished task). PROJECT_CONTEXT roadmap marked authoritative: **15 phases** (22-phase draft superseded); doc map extended.
- Suite 26/26 green; ci.yml YAML-validated.

### Phase 3 — freellmpool integration (2026-08-22) ✅
- Dependency `freellmpool==0.11.4` installed (review in docs/ROUTING.md per R8); lock refreshed.
- Adapter contract upgraded: `ProviderAdapter.complete` now returns `AdapterCompletion` (concrete serving provider/model + notes) so provenance records the real route, never "auto"; `AttemptRecord.notes` added; fake adapter + service updated.
- `FreellmpoolAdapter` (`bebshax/llm/adapters/freellmpool_adapter.py`): one virtual route `freellmpool/auto` (window 1M — freellmpool enforces real per-model limits); full error mapping onto the failure taxonomy (its `ContextWindowExceeded` subclasses `AllProvidersExhausted` — caught first); `client_status=429` → RATE_LIMITED; empty replies → MALFORMED_RESPONSE; injectable pool for tests; `aclose()` lifecycle.
- Boundary enforcement: `test_boundary.py` scans the package — provider SDK imports (freellmpool/ollama/litellm/openai/anthropic) allowed only under `adapters/`.
- **Gate B decided: LiteLLM skipped** — justification + revisit trigger in docs/ROUTING.md.
- **Live keyless smoke PASSED:** served by `llm7/codestral-latest`, zero keys, 3 internal freellmpool failover attempts captured in provenance notes; 33 s latency (keyless tiers are slow — team keys will improve this).
- Suite: 26/26 green (9 new tests). Repo published: https://github.com/Tayebbb/BebshaX (public) + team docs PROJECT_CONTEXT.md / RULES.md / docs/TEAM_SETUP.md.

### Phase 2 — LLM abstraction (2026-08-22) ✅
- `bebshax.llm` package: `TaskType` (16 task types — callers declare their task; no LLM classifies), `ChatMessage`/`LLMRequest`/`LLMResult`, `ProvenanceRecord`+`AttemptRecord` (all §14 fields: provider, model, routing path, attempt no., latency, tokens, failure/fallback reasons, final model).
- Failure taxonomy: 13 `FailureKind`s, each with an explicit `FailurePolicy` (retry-same-once / try-next / cooldown). **Quality is deliberately NOT a failure kind** — enforced by `test_low_quality_is_not_an_infrastructure_failure`. `INTERNAL_ERROR` surfaces immediately instead of burning candidates.
- Adapter boundary: `ProviderAdapter` + `RouteCandidate` in `bebshax/llm/adapters/` — the only package allowed to import provider SDKs. `FakeAdapter` provides scriptable failure injection for tests/chaos.
- `SingleAdapterLLMService`: reference implementation — pre-flight capability + context-window eligibility (ineligible routes are never called; oversized requests raise `ContextWindowExceeded`, never truncate), policy-driven fallback, provenance hook (`on_provenance`) firing on success and failure (Phase-6 DB attachment point).
- Token estimation: chars/4 heuristic + expected output, marked for replacement by the Phase-5 estimator.
- Tests: 14 new (taxonomy, 429→timeout→success chain, same-route retry, all-fail provenance, internal-error surfacing, context skip/explicit-fail, JSON/tool capability filtering, provenance completeness on success + failure). Suite: 17/17 green.
- No new dependencies.

### Phase 1 — Foundation (2026-08-22) ✅
- Repo initialized; scaffold: `apps/backend` (package `bebshax`), `data/{raw,processed,metadata}`, `docker-compose.yml`, `.env.example`, `.gitignore`, `README.md`.
- Config: pydantic-settings with `BEBSHAX_` prefix. Provider keys deliberately NOT modeled in `Settings` — freellmpool reads standard env vars directly, keeping the provider list configuration-driven (owner decision #10).
- Dependencies added (all permissive-licensed, actively maintained, minimal set): `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`; dev-only: `pytest`, `pytest-asyncio`, `httpx`. Exact versions snapshotted in `apps/backend/requirements.lock`.
- **Finding:** native PostgreSQL 16 lacks pgvector (`vector.control` absent) → app DB is `pgvector/pgvector:pg16` on port **5433** (native keeps 5432). Compose file validated with `docker compose config`; container start deferred to Phase 6.
- Verified: 3/3 tests green; live `GET /api/health` → 200 `{"status":"ok","app":"BebshaX","version":"0.1.0",...}`.
- Known item: starlette TestClient emits a deprecation warning suggesting `httpx2`; revisit when starlette requires it.
- Deviation from earlier draft: 22-phase plan replaced by the owner's 15-phase structure (recorded above).
