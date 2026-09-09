# BebshaX — Complete Project Summary (Exhibition Briefing)

> Purpose: one self-contained document that explains the whole project — what it is, what a user does, how every feature works, the technical design, how personas are made, how the chat/LLM layer works, which model was trained on which data and how it was evaluated — plus honest limitations and a judge Q&A. Everything below was checked against the code and the verification records on 2026-09-09. Deep-dive documents are linked at the end.

---

## 0. The 60-second pitch (memorize this)

**BebshaX is an AI market-research platform for zero-budget founders.** You describe a business idea in a chat; the system researches the market, builds a panel of *synthetic customers* ("personas"), lets you interview them, runs behavioral experiments (pricing, feature choice, messaging) on the whole panel, and writes a validation report — all on **$0 of AI budget**.

Three things make it more than "ask ChatGPT":

1. **Reliability from free chaos.** All language-model work runs on legitimately accessed *free* tiers (~18 providers through the `freellmpool` library, OpenRouter's free tier, and a local Ollama model on a laptop GPU) behind a custom routing layer with failover, quotas, cooldowns and a full audit trail. Unreliable free endpoints behave like one reliable API — and the system **never silently degrades quality**: if the full persona context cannot fit a model, it fails loudly instead of cutting context.
2. **A real, trained machine-learning model owns persona generation.** Personas are *not* written by an LLM. A CPU-only TF-IDF + NMF + diversity-selection model, trained on a licensed synthetic profile dataset (NVIDIA Nemotron-Personas-USA, CC-BY-4.0), selects coherent synthetic profiles that match the business context. No API key, no GPU, ~33 ms per five-persona batch.
3. **Honesty is enforced by code.** Every persona claim carries a provenance label — `OBSERVED` (cites real evidence the model was shown), `INFERRED`, or `SYNTHETIC` — and citation checks run in code, not on trust. Demo content is labelled `CACHED`. Every AI request is logged with which providers were tried, why they failed, and who finally answered.

**Research question:** *Can intelligent multi-model routing aggregate free LLM capacity while preserving synthetic persona quality and user experience?*

---

## 1. The problem and the solution

### The problem
Real user research is the most-skipped step in building a product because it is **slow** (weeks to recruit participants), **expensive** (agencies charge thousands of dollars), and **inaccessible** (a student founder in Dhaka cannot afford either). "Just ask ChatGPT" gives generic, sycophantic answers with no grounding and no way to tell fact from invention.

### The solution
BebshaX simulates the whole research pipeline as a **rehearsal before real customer research** (never a replacement):

1. You describe your idea to a Study Design Copilot.
2. The system builds a research goal, suggests customer roles, researches the market, and imports relevant datasets.
3. A trained ML model selects a panel of synthetic personas matching the business context.
4. You interview the personas one-on-one or in batch; they answer in character, remember earlier answers and stay numerically consistent.
5. You run behavioral tests (pricing, feature choice, message A/B, offers) across the panel.
6. The system synthesizes a versioned validation report with an honest limitations section.

### The four honesty promises
1. **Quality is never silently degraded** — oversized context → explicit `ContextWindowExceeded` error, never truncation.
2. **Every AI answer is traceable** — a provenance record per request (providers tried, failures, who served it, latency, tokens).
3. **Every persona claim is labelled** (`OBSERVED` / `INFERRED` / `SYNTHETIC`); fabricated citations are detected and downgraded automatically.
4. **Free-tier use is legitimate** — no fake accounts, no rate-limit evasion; quotas are drained evenly and backed off exactly as providers signal.

---

## 2. Users and roles

| Role | What they can do |
| --- | --- |
| Registered user (founder/researcher) | Everything: create studies, run research, generate personas, interview, test, get reports. Each user sees only their own studies (per-row tenancy by `owner_id`). |
| Anonymous / demo visitor | Explore shared demo content (studies flagged `is_demo`, rows in the shared public pool). Cannot see private work. |
| Admin | **Deliberately none.** Single-tier research tool; the "Model Router" dashboard is observability, not administration. |

Sign-in: email + password with a 6-digit OTP verification email (Resend), or Google via Neon Auth with **server-side** token verification. Sessions are signed JWTs (HS256, 1-day default expiry, refresh endpoint, secret rotation window).

---

## 3. The end-to-end user workflow (what the judges will see)

A user clicks **New Study**, types an idea (e.g. *"An AI meal-planning app for university students in Dhaka at ৳250/month"*), and enters a guided **5-step Study Workflow**:

| Step | Name | What the user experiences | What happens under the hood |
| --- | --- | --- | --- |
| 1 | **Context** | A Study Design Copilot interviews *you* (2–3 turns: target market, key assumption, main risk), then shows a **Research Goal card** (summary, target audience, core hypothesis) to approve, plus 4–8 suggested **persona roles** with adjustable headcounts (1–3 each). | `POST /api/study/copilot` → `TaskType.STRUCTURED_OUTPUT` → structured pool (OpenRouter → freellmpool → Ollama). The model must answer in strict JSON; unparseable replies raise a coded error (`copilot_reply_unparseable`), never canned dialogue. Prompt-injection rule in the system prompt. Study titles are deterministic (regex, no LLM). |
| 2 | **Personas** | One persona per selected role slot appears: name, age, occupation, location, education, description, goals, pain points, behaviors, `SYNTHETIC` provenance chips and a grounding score. | `POST /api/study/generate-personas` → **ML model** (`MLPersonaAdapter`), *no LLM call*. Goal card + role become a strict `BusinessContext`; the model selects complete synthetic source profiles; previous cohort is archived; all claims are `SYNTHETIC`, evidence IDs empty, grounding 0.0. Missing model → 503; unsupported context → 422. |
| 3 | **Script** | An editable interview script (question list) generated from the study goal. | `POST /studies/{id}/script/generate` → LLM (JSON), placeholder-echo detection, JSON repair for small local models. |
| 4 | **Interviews** | Live one-on-one chat with a persona (streamed token-by-token), or a **batch run** across the whole panel with progress polling. Personas remember earlier turns and keep numbers consistent. | `TaskType.PERSONA_INTERVIEW` → conversation pool (Ollama-first). Per-turn identity card + business context + evidence + retrieved memories + **full untruncated history**. Reply normalization, topic classification, numeric-consistency guard, memory write-back, structured insights on completion. |
| 5 | **Report** | A versioned multi-section validation report: executive summary, findings, pain points, pricing signals, risks, opportunities, recommendations, limitations. Copy/export. | `TaskType.REPORT_GENERATION` → long-context pool. Strict rule: use only the study's stored data; never invent; label simulation signals vs empirical evidence. `study_reports.version` auto-increments. |

Supporting features reachable from the sidebar (Workspace / Study / System groups):

| Feature | What it does | How it works |
| --- | --- | --- |
| **Dashboard** | All your studies, status, recent activity. | `GET /studies` with a 2 s TTL client cache invalidated on every mutation. |
| **Persona Library** | Every persona across studies; open profile; save reusable **audiences** (named panels). | `saved_audiences` table; `ProvenanceChip` per claim; `SYNTHETIC` badge for ML personas. |
| **Interviews hub** | All interviews per study with metrics (turn counts, decision state, insight counts) and per-interview **structured insights** linked to the exact turn. | `interview_insights` table; insights extracted at `complete()`; labels coerced to DB limits. |
| **Behavioral Testing** | Define tests (pricing, feature choice, message, offer), run across the panel, see distributions, per-segment differences, auto-extracted risks/opportunities; retry failures; compare tests. | `TaskType.BEHAVIORAL_SIMULATION` per persona → schema-validated decision JSON → aggregation in Python (not asked from an LLM). Scenario text isolated as untrusted input. |
| **Evidence Laboratory** | The research engine's output: research plan, sources, claims coloured green/amber/red (supported / inference / unsupported), semantic search over evidence. | 7-step research pipeline (§9); claims verified against shown chunk IDs; pgvector cosine search. |
| **Datasets** | Upload CSV/JSON/XLSX or fetch a URL; parse, profile (schema + statistics), segment; auto-discover public datasets (World Bank live; Kaggle/BBS illustrative catalogs). | SSRF-guarded fetching, parser, profiler, segmenter, validator (§9.1). |
| **Segmentation** | Cluster the dataset population into named market segments that ground persona allocation. | Deterministic clustering (math) + LLM only for naming/narrative (§9.2). |
| **Model Router** (developer view) | Live provider health, per-pool concurrency, quota consumption, cooldowns, the full provenance log, and the **Judge Lab** failure drills. | `GET /api/routes/status`, `/api/routing/capacity`, `/api/provenance`, `/api/demo-lab/scenarios`. |
| **AI Review** | A rubric-scored second opinion on a study or persona (0–100 per dimension). | `TaskType.CRITIC`; fixed rubric exposed at `GET /api/ai-review/rubric`; non-numeric dimensions omitted, never zero-filled. |
| **Demo mode** | `BEBSHAX_DEMO_MODE=true` seeds a complete sample study; anything from fixtures is badged **CACHED**. | `data_source="cached"` stored per row at creation time, so the truth survives flag flips. |

---

## 4. System architecture

```
React 18 + Vite 5 + TypeScript frontend (apps/frontend)
        │ REST/JSON (+ SSE for streamed interview turns)
FastAPI backend, Python 3.12, fully async (apps/backend, package `bebshax`)
        │
        ├── Feature engines: Copilot · Persona · Interview · Memory · Research/Evidence ·
        │   Datasets · Segmentation · Behavioral · Reports · AI Review · Auth · Payments (scaffold)
        │
        ├── bebshax.llm — the LLM policy layer (custom)
        │     LLMService = PoolRouter: task → pool → ranked candidates → eligibility →
        │     attempt chain → failure policy → provenance record (EVERY call)
        │     adapters/ (the ONLY place provider SDKs may be imported — test-enforced):
        │       FreellmpoolAdapter (~18 free providers) · OpenRouterAdapter (free tier) ·
        │       OllamaAdapter (local llama3.2:3b / qwen3:4b) · FakeAdapter (tests)
        │
        └── ml_persona — independent Python package `bebshax_persona_ml` (no LLM, no GPU)
              TF-IDF + NMF + diversity-aware selection over licensed synthetic profiles
              loaded server-side through MLPersonaAdapter
        │
PostgreSQL 16 + pgvector (Docker, port 5433) — users, studies, personas, evidence chunks,
memory vectors, interviews, behavioral results, reports, llm_requests (provenance), model_registry
```

### Stack

| Layer | Choice | Why |
| --- | --- | --- |
| Backend | Python 3.12 + FastAPI (async), Pydantic v2, SQLAlchemy 2 async, Alembic | I/O-bound workload (waiting on LLMs); freellmpool and the dataset ecosystem are Python; runtime-validated contracts everywhere |
| LLM routing | `freellmpool` (MIT) as a *library* + OpenRouter free tier + Ollama, behind a custom policy layer | Existing OSS → thin adapter → custom BebshaX logic; LiteLLM/proxies rejected as heavy infrastructure |
| Persona ML | scikit-learn (TF-IDF, NMF), SciPy, NumPy — CPU only | Small specialized model beats another LLM for this task; runs on any laptop; no key, no network |
| Database | PostgreSQL 16 + pgvector in Docker (port 5433) | One database for relational + vector data; native PG16 on the dev machine lacks pgvector |
| Frontend | React 18 + TypeScript + Vite 5, Tailwind-assisted CSS with a semantic design-token theme (dark/light), GSAP motion, Vitest | Instant HMR, TypeScript-first; single-page app with tab routing |
| Auth | JWT (HS256), Resend for OTP email, Neon Auth for Google sign-in | Stateless SPA + API; server-side identity verification |
| Rate limiting | slowapi | Per-endpoint limits on LLM-spending and auth routes |
| Deployment | `docker compose` (db; `--profile full` adds API + nginx web), one-shot `scripts/setup.py`, `node scripts/dev.js` | Boring, reproducible, no Kubernetes/Redis/queues by rule |

### Repository layout

| Path | Purpose |
| --- | --- |
| `apps/backend/bebshax/` | FastAPI app: `api/` routers, `llm/` policy layer + adapters, `persona/` + `personas/` engines, `interview/`, `memory/`, `research/`, `datasets/`, `segmentation/`, `behavioral/`, `evaluation/`, `db/`, `auth/` |
| `apps/frontend/src/` | Landing page, auth pages, dashboard shell, study workflow (Step 1–5), persona library, interview workspace, behavioral testing, evidence lab, segmentation, model router |
| `ml_persona/` | Independent ML package: `src/bebshax_persona_ml/{data,model,pipeline,evaluation,cli}.py`, tests, `configs/training.json`, `constraints.txt`, README / MODEL_CARD / EXPERIMENTS / DATASETS / ARCHITECTURE |
| `scripts/` | `setup.py`, `dev.js`, `setup_datasets.py` (profiles), evaluation/benchmark/audit scripts |
| `data/` | `raw/`, `processed/` (Git-ignored), `metadata/` (manifests, benchmark and audit records) |
| `docs/` | Architecture, routing, failover, persona engine, evaluation, API contract, setup, demo, implementation log |

Three hard architectural rules (all test-enforced): **R1** provider SDKs only inside `llm/adapters/`; **R3** every LLM call goes through `LLMService.complete(LLMRequest)` with an explicit task type and produces a provenance record; **R2** nothing may truncate persona identity/memory/evidence to fit a model.

---

## 5. How the LLM / chat layer works

> Think of an airport control tower. Every AI request arrives labelled with what kind of work it is. The tower looks up which runway group (pool) handles that work, lines up the available planes (providers) in a smart order, skips the ones that are too small (context window), grounded (cooling down) or out of fuel (quota), then tries them one by one. Every attempt is written in a flight log.

### 5.1 Task types (18, fixed — callers declare intent, no LLM classifies requests)
`PERSONA_GENERATION, PERSONA_REFINEMENT, PERSONA_VALIDATION, PERSONA_INTERVIEW, PERSONA_RESPONSE, EVIDENCE_EXTRACTION, EVIDENCE_CLASSIFICATION, MEMORY_RETRIEVAL, MEMORY_SUMMARIZATION, CONTRADICTION_CHECK, CRITIC, REPORT_GENERATION, STRUCTURED_OUTPUT, BROWSER_AGENT, TOOL_CALLING, PERSONA_NARRATIVE, BEHAVIORAL_SIMULATION, EMERGENCY_FALLBACK`.
(The persona-generation task types remain for compatibility; production persona generation now uses the ML model, not an LLM.)

### 5.2 Pools — configuration as data (7 pools, `pools.py`)

| Pool | Adapter order | Max concurrency | Serves |
| --- | --- | --- | --- |
| `reasoning` | openrouter → freellmpool → ollama | 2 | critic, contradiction check, narratives, behavioral simulation |
| `conversation` | **ollama → freellmpool → openrouter** (local-first) | 5 | interview turns, persona responses |
| `long_context` | openrouter → freellmpool → ollama | 2 | report generation |
| `structured` | openrouter → freellmpool → ollama | 3 | JSON extraction, copilot, tool calling |
| `fast` | ollama → freellmpool → openrouter | 5 | memory retrieval/summarization |
| `local` | ollama | 2 | forced-local work |
| `emergency` | ollama → freellmpool | 2 | `EMERGENCY_FALLBACK` |

A test enforces that every task type maps to a pool. The conversation pool is local-first because a judged quality gate scored the local 3B model 9.65 / 9.05 / 9.2 across three runs (vs 8.25 / 8.05 / 8.2 for the cloud-fast route) at ~5–7 s/turn — small sample (1 persona × 5 questions), but consistent.

### 5.3 The request lifecycle (`PoolRouter.complete()`)
1. task → pool (data lookup); 2. acquire the pool semaphore; 3. collect route candidates from each adapter in pool order; 4. **quota-aware ranking** (drain all free quotas evenly); 5. user-preferred provider/model moved to the front (advisory, never exclusive); 6. **eligibility filter**: cooldown active? JSON mode/tools unsupported? context window smaller than the estimate? — skipped candidates are recorded with the reason; if only context exclusions emptied the list → `ContextWindowExceeded`; if nothing is eligible → `AllCandidatesFailed`; 7. **attempt loop**: success → record the concrete serving provider/model; failure → consult the policy table for that failure kind (retry same once / try next candidate / cooldown route); 8. every path emits a complete `ProvenanceRecord`.

Pre-flight token estimation is deterministic (`chars/3.5 + 4 per message + expected output`) and deliberately *over*-estimates: the only side effect is steering to roomier models; it can never cause truncation.

### 5.4 The closed failure taxonomy (13 kinds)
`TIMEOUT, CONNECTION, RATE_LIMITED, QUOTA_EXHAUSTED, SERVER_ERROR, PROVIDER_UNAVAILABLE, AUTH_INVALID, MODEL_UNAVAILABLE, CONTEXT_WINDOW_EXCEEDED, CAPABILITY_UNSUPPORTED, MALFORMED_RESPONSE, CONTENT_REFUSAL, INTERNAL_ERROR` — each with a 3-flag policy. Two deliberate exclusions: **"low answer quality" is not a failure kind** (a boring answer must never trigger silent infrastructure fallback; quality belongs to the evaluation layer), and **`INTERNAL_ERROR` never advances the fallback chain** (our own bugs surface instead of burning provider quota).

### 5.5 Streaming commitment rule
Interview turns stream over SSE. Failover happens only **before the first token**; once a route has produced visible text the stream is committed — a mid-answer provider swap would splice two voices.

### 5.6 Capacity management ($0 budget machinery)
- **QuotaLedger** — published free-tier caps per provider (e.g. OpenRouter free: 20 requests/min, 50/day), per-UTC-day counters seeded from the `llm_requests` table at startup.
- **Quota-aware ranker** — sorts candidates by remaining fraction (stable sort).
- **Persistent cooldowns** — 60 s per (provider, model) on rate-limit/server errors, mirrored to `model_registry.cooldown_until`; provider-scoped cooldowns for quota/auth failures; half-open probes to recover a route.
- **Latency seeding** — measured per-route latencies replayed from provenance at boot.
- Everything is fail-soft: capacity features can never take the request path down.

### 5.7 Provenance (the audit trail)
Every request produces: request id, task, pool, persona/conversation ids, the ordered routing path with skip reasons, every attempt (provider, model, latency, failure kind, fallback reason), the concrete serving provider/model, token counts, total latency, success flag. A batched fail-soft `ProvenanceSink` writes to `llm_requests`; DB trouble never fails an LLM call. Served in the Model Router view via `GET /api/provenance`.

### 5.8 Adapters
- **FreellmpoolAdapter** — wraps the MIT `freellmpool` async pool (~18 free providers, keyless start, internal circuit breakers). Resolves virtual routes to the *concrete* provider/model (e.g. `llm7/codestral-latest`) so provenance stays truthful.
- **OpenRouterAdapter** — direct OpenRouter free tier; catalogue discovered live (free model IDs drift); 402 → quota exhausted; reasoning disabled where offered so replies are not empty.
- **OllamaAdapter** — native `/api/chat` (only path that pins `num_ctx`; the OpenAI-compat shim silently truncates); `format: "json"` for JSON mode (grammar-constrained decoding fixed invalid JSON from the 3B model: 0/3 → 5/5 valid on the full report prompt); models: `llama3.2:3b` primary, `qwen3:4b` secondary, chosen by benchmark for the 4 GB-VRAM laptop GPU.
- **FakeAdapter** — deterministic test double; real providers are never called in CI.
- **Embeddings** — default deterministic 384-dim hash embedding (offline, free, stable); optional Ollama/freellmpool embeddings. Every vector is tagged with its `embedding_space`; retrieval never compares vectors from different spaces.

### 5.9 Judge Lab (live failure drills for the exhibition)
`GET /api/demo-lab/scenarios` + `POST /api/demo-lab/scenarios/{name}/run` build a throwaway `PoolRouter` over scripted fake routes and run the **real** routing code path. Seven scenarios: *Provider returns 429 → fallback serves* · *5xx then timeout → local route serves* · *Every provider down → explicit failure* · *Prompt exceeds every context window → refuse, never truncate* · *Evidence chunk carries a prompt injection* · *Two evidence items disagree on age* · *No evidence retrieved → 0% grounding shown honestly*. Every payload says `"simulated": true`; nothing touches real providers. Shown in the Model Router view.

---

## 6. How persona making works (the trained ML model)

### 6.1 Why a separate ML model instead of asking the LLM
- The LLM layer already handles conversation and collects business context. Persona *generation* needed a specialized, auditable, key-free component with training data, evaluation and reproducibility.
- A prompt is not a model. The subsystem has: dataset ingestion with license checks → normalization → identity-disjoint splits → a fitted model (vocabulary, IDF weights, topic components, profile representations) → hyperparameter selection on validation → one held-out test → serialized artifacts with integrity checks → inference through a backend adapter → tests (298).
- Rule R9 forbids LLM fine-tuning. The owner-approved exception (2026-09-08) permits training a **non-LLM** model on reviewed *public synthetic* data only; private studies, uploads and conversations are never training inputs.

### 6.2 What the model does (in one sentence)
It learns a representation of thousands of complete synthetic customer profiles and, given a business context, **selects whole coherent profiles** that match it, with a diversity penalty so five requested personas are five different kinds of people. It does **not** write new identities (a bag-of-words model cannot write coherent biographies) and never splices attributes across people (which would create contradictions like a 19-year-old senior executive). Exact reuse of a source profile is intentional and every claim is labelled `SYNTHETIC`.

### 6.3 Training data — research, licensing, provenance

| Dataset | License | Decision |
| --- | --- | --- |
| **NVIDIA Nemotron-Personas-USA** (`nvidia/Nemotron-Personas-USA`, revision `5b4cd35ab46490c1da1bd2b5a2324d6f871be180`, v1.1) | CC-BY-4.0 (re-verified from the pinned dataset card) | **Used.** 1,000,000 synthetic adult profiles grounded in US Census distributions; 22 fields incl. six persona narratives, age, occupation, education, city/state/country. Generated by NVIDIA with a probabilistic graphical model + an open LLM; no real people. |
| Google Synthetic-Persona-Chat | CC-BY-4.0 | Researched, not used for ML: conversation-centric, no structured demographics (kept for legacy dialogue examples). |
| PersonaHub | CC-BY-NC-SA-4.0 | Not used for ML: non-commercial/share-alike restrictions, insufficient structure (legacy seed use unchanged). |
| UCI Restaurant Consumer Data | CC-BY-4.0 | Researched, **not downloaded**: real people (138), coordinates/religion → privacy; narrow domain; violates the synthetic-only rule. |
| `sentence-transformers/all-MiniLM-L6-v2` | Apache-2.0 | A pretrained *embedding model*, researched but not used: adds a transformer runtime and a 256-wordpiece truncation policy; the baseline trains locally without it. |

Ingestion (`scripts/setup_datasets.py --profile ml_persona`): official `hf_hub_download` with `token=False`; the card must declare exactly `cc-by-4.0` or the download aborts; upstream LFS SHA-256 verified; **one shard** (`data/train-00000-of-00011.parquet`, 244,151,718 bytes) scanned completely (90,910 rows, 5 row groups); **6,000 profiles** selected as the lowest SHA-256 ranks of `<repo>@<revision>:<uuid>` (deterministic, not a prefix, not a random sample); 17 allowlisted fields projected; `sex`, `zipcode`, `marital_status`, `bachelors_field` and list variants dropped; nothing truncated; output 30,146,176 bytes of JSONL with recorded checksums. `--verify-only` re-checks everything offline; `--force` rebuilds from the pinned source.

### 6.4 Data preparation (`python -m bebshax_persona_ml prepare`)
- **Normalization** into a typed `TrainingRecord`: Unicode NFKC + whitespace normalization; `record_id = sha256(source, uuid)`; age must be an integer in 18–95; occupation/education/location from structured fields; a name is extracted from the narrative only when it clearly starts with one; **goals** = `career_goals_and_ambitions`; **pain points** = narrative sentences containing constraint words (`budget, cost, struggle, limited, lack, difficult, challenge, barrier, concern, worry, pressure, constraint, unaffordable, frustrat…, dislike, need`) — weak labels, not ground truth; **behaviors** = hobbies/interests + the persona narrative; all narratives kept in full as `documents`. Records containing e-mail addresses/URLs are rejected.
- **Quality pass**: 6,000 rows → **4,694 accepted / 1,306 rejected** (strict schema) → **1,078 incomplete** removed (missing goal or pain-point sentences etc.) → **22 duplicate identities** removed → **3,594 usable candidates**.
- **Splits**: seed 42, 70/15/15 → **2,516 train / 539 validation / 539 test**, disjoint by identity (record id, name, and narrative). Validation re-derives the canonical records and split membership from the approved source, so a substituted claim cannot be smuggled in by re-hashing files.

### 6.5 Model architecture (`tfidf-nmf-mmr-v1`)
1. **Feature text** per profile: description, occupation, education, location, goals, pain points, behaviors and all narratives **except protected fields** (`sex`, `religion`, `race`, `cultural_background` are removed from features; the extracted name is also removed so the model cannot match on names).
2. **TF-IDF** (`TfidfVectorizer`, English stop words, **8,000 features**) fitted on training profiles only → learned vocabulary and inverse-document-frequency weights.
3. **NMF** (non-negative matrix factorization, **32 topics**, `nndsvda` init, seed 42, ≤300 iterations) on the TF-IDF matrix → latent topic components; each profile gets an L2-normalized topic vector.
4. **Scoring** a business context (`BusinessContext.text()` = description, target audience, location, price range, category, features, research, role):
   `score = 0.7 × cosine(TF-IDF) + 0.3 × cosine(topics)`, clipped to [0, 1] (lexical weight 0.7 was selected on validation).
5. **Selection** (maximal-marginal-relevance style): hard filters first (explicit `min_age`/`max_age`, excluded source IDs/names already active for this owner); then for each of *n* personas: `utility = score − 0.25 × redundancy` (redundancy = max similarity to already selected profiles), softmax with **temperature 0.03** (near-greedy but seeded), sample without replacement, update redundancy. Role and location are *soft* relevance hints — the source occupation/location is retained and a warning is attached when the requested location is not established.
6. **Output**: `Selection(record, score, topic, warnings, model_version)`. Scores are retrieval similarity, **not** confidence or purchase probability.

### 6.6 Training procedure and reproducibility
- Config `ml_persona/configs/training.json`: grid over topics {16, 32} × lexical weight {0.35, 0.70}; seed 42; 8,000 features; 300 iterations; diversity 0.25; temperature 0.03; 2 CPU threads; `device: cpu` (`cuda` is deliberately rejected).
- Selection objective: validation `retrieval.model.mrr`; ties broken deterministically. The test split is never used for selection and was evaluated exactly once after the choice was frozen.
- Hardware/time: Windows 11 laptop, Intel Core i5-12500H (16 logical CPUs), 2 threads → the four fits took **43.70 s total**. No GPU used (the RTX 3050 4 GB stays free for Ollama).
- Recorded runtime: Python 3.12.9, NumPy 2.5.2, SciPy 1.18.1, scikit-learn 1.9.0 — pinned in `ml_persona/constraints.txt` and applied in the Docker image (an unpinned image resolved NumPy 2.5.3 and the loader correctly refused the mismatch).
- Artifact (`data/processed/ml_persona/model/`, Git-ignored, ~32.5 MiB): `config.json`, `metadata.json`, `vocabulary.json` (137 KB), `records.json` (19.5 MB, the training profiles), `parameters.npz` (14.5 MB). Loaded with `allow_pickle=False`, per-file SHA-256 checks, bounded sizes, exact shape/dtype/finite/non-negative validation, exact numerical-version match. Model version `7eb2fa6f748fac32…` = hash(corpus, config, algorithm). Every experiment is recorded in `experiment.json` / `experiments/<version>.json` (seed, dataset fingerprints, hyperparameters, timings, runtime, hardware, all candidate metrics).

### 6.7 Evaluation — protocol and results

**Retrieval proxy (held-out, 539 identities).** Query view = culinary + hobbies narratives; candidate view = professional/sports/arts/travel/skills/goals narratives of the *same held-out people*. Using training-fitted transforms only, rank all 539 candidates for each query; the correct match is the other view of the same identity.

| Method | Test MRR | Recall@1 | Recall@5 | Recall@10 |
| --- | --- | --- | --- | --- |
| **Selected TF-IDF + NMF blend (32 topics, 0.7 lexical)** | **0.4327** | 0.3414 | 0.5306 | 0.6141 |
| Lexical TF-IDF baseline | **0.7516** | 0.6605 | 0.8720 | 0.9295 |
| Expected uniform random | 0.0127 | 0.0019 | 0.0093 | 0.0186 |
| Training occupation-frequency ranking | 0.0119 | 0.0019 | 0.0093 | 0.0130 |

Validation grid (MRR): 16/0.35 → 0.197; 16/0.70 → 0.369; 32/0.35 → 0.238; **32/0.70 → 0.418**; lexical baseline 0.717.

**Say this plainly to judges:** the model is far above random, but **the NMF topic blend underperforms the plain TF-IDF baseline** on this proxy. We froze the selection before looking at the test set and report the result instead of retuning on it. The next validation-only experiment is a pure TF-IDF + diversity selector, plus a real business-labelled relevance evaluation.

**Generation probes (test split, 32 batches × 5 = 160 personas):** 0 failed batches; 0 incomplete/underage profiles; 0 duplicate IDs/names/descriptions within a batch; 0 bundle mismatches or location rewrites; exact source reuse 100 % (by design); mean within-batch cosine distance **0.878** (diverse); age distribution Jensen-Shannon divergence vs held-out reference **0.030** (close); occupation coverage 17 %, topic coverage 66 %; **72/160 selections were `not_in_workforce`** — a visible selection bias we report. Warm latency: mean 33.0 ms, p95 **34.3 ms** per five-persona batch on 2 CPU threads (excludes cold load, API, DB).

**Baselines compared** (as the brief asked): random sampling, frequency (occupation popularity) ranking, lexical TF-IDF retrieval, and the final blended model.

### 6.8 Integration into BebshaX (four generation paths, one adapter)
`apps/backend/bebshax/personas/ml_adapter.py` (`MLPersonaAdapter`) is the single boundary: lazy-loads the artifact once, runs inference off the event loop with bounded concurrency, converts `Selection` → the **existing** `GeneratedPersona` / `PersonaProfile` / `GeneratedPersonaDraft` contracts and JSON columns (no new schema, no migration). Paths: (1) legacy `POST /api/businesses/{id}/personas`; (2) study `POST /studies/{id}/personas/generate` (+ async jobs, regenerate); (3) role-based workflow `POST /api/study/generate-personas` (Step 2); (4) dataset-based `POST /api/datasets/{id}/generate-personas`.
Contract: all goals/pain points/behaviors are `SYNTHETIC` with empty evidence IDs; grounding 0.0; income/budget = "Not available in training data"; personality (Big Five) unset — never invented; `detailed_attributes.ml_provenance` stores source repo, revision, record id, model version, score and topic; `generation_model = bebshax-persona-ml/<version>`. Sequential requests exclude source identities already active for the same owner/study; the role-based path archives the previous cohort. Missing/incompatible artifact → **503 `ml_persona_unavailable`**; unsupported ages/no vocabulary overlap/too few distinct candidates → **422 `ml_persona_unsupported_context`**. **There is no LLM fallback for persona generation**; chat and interviews keep working when the artifact is absent (tested).

### 6.9 Reproduce it (from the repo root)
```powershell
.venv/Scripts/pip.exe install -c ml_persona/constraints.txt -e ml_persona -e "apps/backend[dev]"
.venv/Scripts/python.exe -m bebshax_persona_ml download     # pinned, license-checked source
.venv/Scripts/python.exe -m bebshax_persona_ml prepare      # normalize, dedupe, split
.venv/Scripts/python.exe -m bebshax_persona_ml validate     # canonical source + split checks
.venv/Scripts/python.exe -m bebshax_persona_ml train --config ml_persona/configs/training.json
.venv/Scripts/python.exe -m bebshax_persona_ml evaluate     # held-out test, once
.venv/Scripts/python.exe -m bebshax_persona_ml generate --input ml_persona/examples/business.json --num-personas 5
.venv/Scripts/python.exe -m bebshax_persona_ml smoke --backend --input ml_persona/examples/business.json
```
The CLI is JSON-only, refuses to overwrite outputs without `--force`, keeps every path inside the root, and never contacts an LLM.

---

## 7. How interviews stay in character (interview engine + memory)

Per turn (`interview/engine.py`):
1. **Immutable identity card** rebuilt deterministically from the stored persona (name, age, occupation, location, education, description, goals, pain points, behaviors) and asserted byte-identical across the conversation (test-enforced — identity cannot drift).
2. **Layered system prompt**: identity card + grounded-behavior rules + business context + study goal/audience/pricing hypothesis + segment traits + top-3 evidence citations + interview objective + top-k **retrieved memories** ("stay strictly consistent").
3. **Full history, never truncated** — if nothing fits, explicit `ContextWindowExceeded`.
4. `PERSONA_INTERVIEW` → conversation pool (local-first); streaming to the UI.
5. **Deterministic post-processing**: strip reasoning-model `<think>` leaks, markdown fences and "Name:" script prefixes (format ≠ content; never rewrite content); classify the exchange into 9 research topics for coverage tracking; **numeric self-consistency guard** (currency cue tables for ৳/BDT, $, £, €, ₹, KSh, Rp, ₦; daily amounts normalized to monthly; contradictions flagged); write the exchange to memory (importance 0.4).
6. **Completion**: structured, turn-linked insights + decision-state evaluation; insights whose labels exceed DB limits are coerced, never dropped silently (`insights_dropped` is reported).

**Memory (pgvector, `memory/service.py`)**: observations embedded (384-dim) into `memory_items`; retrieval score = **0.60·cosine + 0.25·recency (48 h half-life) + 0.15·importance**; HNSW cosine index on Postgres; periodic **reflection** summarizes episodic items into higher-level insights (importance 0.8) — the "Generative Agents" idea re-implemented. Remembering a simulated statement does not make it customer evidence.

---

## 8. Research engine, datasets, segmentation, behavioral tests, reports

### 8.1 Autonomous research engine (7 steps, live progress)
`understanding_idea → building_research_plan → searching_evidence → discovering_datasets → evaluating_datasets → importing_datasets → extracting_evidence`
- Research plan (`STRUCTURED_OUTPUT`): target market, problem areas, four question banks, dataset requirement specs.
- Query generation (5–7 queries across problem/competition/pricing/behavior/complaints).
- Source collection through a `SearchProvider` interface with URL canonicalization and content-hash dedup. **Default corpus is a clearly-labelled illustrative sample** ("BebshaX Illustrative Sample") — never attributed to real publishers; a live search provider plugs into the same interface.
- Chunking (~400 chars, sentence boundaries, 40-char overlap) → embeddings → `evidence_chunks` (pgvector).
- Dataset discovery via adapters: **World Bank Open Data is live** (keyless `api.worldbank.org`, Bangladesh indicators, labelled `is_sample=false`); Kaggle and Bangladesh Bureau of Statistics adapters are **illustrative catalogs** modelled on the real sources and badged SAMPLE.
- Claim extraction (`EVIDENCE_EXTRACTION`): claims classified supported / inference / unsupported; a "supported" claim citing a chunk the model was never shown is downgraded with a note; the keyword fallback extractor never claims "supported".
- Semantic search over the study's chunks.

### 8.2 Dataset toolchain
`security.py` (SSRF defense: scheme allowlist, private/loopback/link-local IP blocking, no redirects, size cap) → `parser.py` (CSV/JSON/XLSX/TSV) → `profiler.py` (schema + per-column statistics) → `segmenter.py` (population segments and proportional persona allocation) → `validator.py` (checks personas against observed dataset constraints). Rows carry a `content_hash`; a status machine (`idle → fetching → parsing → profiling → analyzing → ready | error`) drives the UI. Uploads are never used for ML training.

### 8.3 Segmentation
Readiness pre-check → variable selection → **deterministic clustering (math, reproducible)** → LLM only for naming/narrative ("Hall-resident budget optimizers"). Stored as `segmentation_runs` + `market_segments`; segments supply generation hints and interview context.

### 8.4 Behavioral testing
Test types: pricing, feature choice, message/copy, offer. Each persona is asked for a schema-validated decision (`decision, probability, confidence, factors, motivators, objections, rationale`) via `BEHAVIORAL_SIMULATION`; the scenario text is wrapped as **untrusted input** (prompt-injection defense). Aggregation (distributions, per-segment differences, risk/opportunity insights with confidence = observed share) is computed in Python. One failed persona never kills a run; `retry-failed` exists. These are simulated choices, not observed demand.

### 8.5 Reports and AI review
`REPORT_GENERATION` over everything stored for the study (evidence, datasets, segments, personas, transcripts, insights, behavioral results) with strict "use only provided data" rules; versioned; empty studies are refused (`report_requires_data`); all report fields are normalized to DB limits. The **AI Review** (`CRITIC`) scores a study or persona against a fixed public rubric, 0–100 per dimension; the model's own words are stored, never fabricated numbers.

---

## 9. Frontend

- **Four surfaces**: a cinematic marketing landing page (~20 sections, custom scroll choreography), the auth flow (sign-in/up, OTP, forgot/reset), the dashboard shell with path-based tabs (New Study, Dashboard, Persona Library, Interviews, Behavioral Testing, Evidence Lab, Segmentation, Model Router, Study Workflow), and a dedicated **Interview Workspace** for live one-on-one interviews (shared `PromptInputBox` composer, streamed replies).
- **One typed API client** (~117 endpoints) with per-call timeout budgets sized to measured latencies (300 s for LLM paths), a mock layer strictly gated to mock/test mode (live failures show errors, never fixtures), 202 + poll helpers for long jobs.
- **Design system**: semantic CSS tokens (`--glass-*`, `--status-*`, `--prov-*`), dark/light themes with an iOS/macOS-inspired visual language, a codemod drift gate (`npm run theme:check`) that fails CI on literal colours; GSAP motion gated by `prefers-reduced-motion`; accessibility (real buttons, dialog focus traps, Escape stacking, ARIA labels, ≥4.5:1 contrast).
- **Honesty in UI**: `ProvenanceChip`s (OBSERVED/INFERRED/SYNTHETIC), `CACHED` badges on demo content, "backend unreachable" banner instead of silent mocks, request-ID tags on errors, route disclosure showing which provider served each reply.
- **Known UI defect**: at 390×844 the persona profile header clips the Regenerate/close controls (the lower Close button works). Desktop verified at 1440×1000.

---

## 10. Data model and API (summary)

30+ tables on one SQLAlchemy `Base`, migrated only by Alembic (the app refuses to serve a local DB that is not at migration head):

| Domain | Tables |
| --- | --- |
| LLM infra | `llm_requests` (provenance, JSONB attempts), `model_registry` (cooldown_until) |
| Identity | `users`, `email_verification_tokens` |
| Studies | `studies` (workflow state, roles, script, copilot transcript, personas payload), `saved_audiences`, `study_reports` (versioned) |
| Personas | `personas` (+ `persona_details`, `persona_attributes`, `persona_evidence`) |
| Research | `research_runs`, `research_plans`, `evidence_sources`, `evidence_chunks` (Vector 384), `evidence_claims`, `dataset_candidates` |
| Datasets | `dataset_sources`, `dataset_persona_runs` |
| Segmentation | `segmentation_runs`, `market_segments` |
| Interviews | `conversations`, `conversation_turns`, `interview_insights` |
| Behavioral | `behavioral_tests`, `behavioral_test_scenarios`, `behavioral_test_runs`, `behavioral_test_results`, `behavioral_insights` |
| Memory | `memory_items` (Vector 384, HNSW cosine) |

API areas (all under `/api`): health, auth, studies, copilot, personas (sync + 202/poll jobs + regenerate), interviews (messages, `/stream` SSE, complete, insights, batch-run), research/evidence, datasets, segmentation, behavioral, reports, AI review, observability (`/routes/status`, `/routing/capacity`, `/provenance`, `/demo-lab`), payments (Stripe scaffold). Long-running work uses in-process `asyncio` jobs that persist their real output as they go — no message queue by rule.

---

## 11. Security and privacy

- Secrets env-only; `BEBSHAX_JWT_SECRET` required (≥32 chars) and one historically leaked value is hard-rejected at boot.
- JWT HS256 with issuer/audience, 1-day expiry, refresh, previous-secret rotation window; Google identity verified server-side via Neon Auth; email verification enforced in production/staging.
- Per-row tenancy in one policy module; foreign rows return **404, not 403** (no existence oracle); rate limiting on auth and LLM-spending routes; explicit CORS origins.
- SSRF-guarded dataset ingestion; prompt-injection isolation of untrusted text (behavioral scenarios, evidence chunks, copilot rule); error envelopes with request IDs and generic messages (internals go to logs/provenance).
- Personas are synthetic; no real PII is ingested; training data is public synthetic data with explicit sex/zip/marital fields dropped; nothing sensitive is sent to free LLM tiers.
- Legitimate free-tier use only (verified that extra OpenRouter accounts do not raise caps — and rejected on principle).
- Dependency audit (`pip-audit`): no known vulnerabilities in the installed environment; Gitleaks secret scan in CI.

---

## 12. Testing, verification and CI (numbers as of 2026-09-09)

| Gate | Result |
| --- | --- |
| Backend test suite (unit + chaos via `FakeAdapter`, SQLite) | **1,287 passed**, 3 DB-integration tests deselected, **81.64 % coverage** (floor 68 %) |
| Independent ML suite | **298 passed**, 97 % coverage |
| Frontend (Vitest) | **269 passed** across 36 files; TypeScript + Vite build clean; theme gate 0 violations |
| Lint (Ruff), `pip check`, Compose config (default + full profile) | Passed |
| Real PostgreSQL/pgvector integration tests | 2 passed on a fresh local database |
| Real five-stage ML smoke (`smoke --backend`) | Passed with the trained artifact: source → prepared → model → generation → backend schema conversion, no LLM/network/DB |
| Docker | Backend image builds with pinned runtime; the Windows-trained artifact loads and selects 5 unique profiles inside the Linux container with `--network none` |
| Live end-to-end (fresh local DB) | 5 unique age-bounded ML personas persisted and reloaded (22 synthetic attributes, 0 LLM generation calls); real copilot reply, 10 role suggestions, 2 interview turns and 4 memory rows via Freellmpool (`llm7/codestral-latest`); desktop UI clean, zero JS errors |
| GitHub Actions (Ubuntu) | Required jobs green on commit `be92185` (backend+ML, frontend, migration-drift, secret-scan, compose); the advisory typecheck job (pre-existing type debt) is non-blocking and still red |

Architecture is enforced by tests: adapter boundary (AST scan for provider imports), task→pool coverage, "quality is not a failure kind", provenance completeness, ML source-integrity (re-hashed forgeries rejected), Docker runtime pins.

---

## 13. Running the demo

```powershell
# one-time
python scripts/setup.py                       # venv, install, .env with a real JWT secret, db container, migrations, datasets, tests, frontend
# every day
docker compose up -d --wait db                 # pgvector on localhost:5433
node scripts/dev.js                            # API http://127.0.0.1:8000  +  frontend http://localhost:5173
```
Before the exhibition: start **Ollama** and make sure `llama3.2:3b` is pulled (local interview tier), confirm the ML artifact exists at `data/processed/ml_persona/model` (or set `BEBSHAX_ML_PERSONA_ARTIFACT_DIR`), and optionally set `BEBSHAX_DEMO_MODE=true` for the seeded sample study (credentials in `docs/DEMO.md`). Offline drill: persona generation is fully offline (local model); chat/interviews fall back to Ollama when cloud tiers are unreachable; cached demo content is badged.

Suggested 8-minute demo: (1) Model Router → show provider status, quota ledger, provenance log; run two **Judge Lab** scenarios (429 → fallback; context overflow → refuse). (2) New Study → Step 1 copilot consultation → approve goal + roles. (3) Step 2 → generate personas (instant, ML; point at `SYNTHETIC` chips and the `bebshax-persona-ml/…` model tag). (4) Open one persona in the Interview Workspace, ask two questions, show the route that served each reply and the memory disclosure. (5) Behavioral pricing test on the panel. (6) Step 5 report → limitations section. (7) Evidence Lab → green/amber/red claims.

---

## 14. SDG and Complex-Engineering-Problem mapping

| SDG | How BebshaX contributes |
| --- | --- |
| **8 — Decent Work & Economic Growth** (8.3) | Removes the two barriers that make founders skip research — weeks of recruiting and thousands of dollars — so ideas get tested before savings are spent. |
| **9 — Industry, Innovation & Infrastructure** (9.b) | The core contribution is infrastructure: a routing layer that turns ~20 free endpoints + a laptop GPU into one reliable substrate; grounded in public open data (World Bank, BBS catalogs). |
| **10 — Reduced Inequalities** (10.2) | Access to AI-powered research does not depend on money: $0 budget as a hard constraint, BDT-first context, local-market grounding. |
| **4 — Quality Education** (4.4, co-benefit) | Provenance-labelled workflow teaches evidence-based validation; every report ends with limitations and a push toward real customers. |

Complex Engineering Problem attributes: **WP1** depth (distributed failover, applied NLP/retrieval, ML evaluation methodology); **WP2** conflicting requirements ($0 vs no silent degradation; full context vs small windows; legitimacy vs throughput; demos vs honesty); **WP3** no obvious solution — decisions made by recorded experiments (local-model gate, capacity study, "quality ≠ infra failure"); **WP4** infrequent issues (mid-conversation provider failover with identity intact; embedding-space corruption solved by space tags); **WP5** beyond standards — the team wrote its own binding engineering code (RULES R1–R12) enforced by tests; **WP6** diverse stakeholders (founders, providers' ToS, open-data licences, populations behind the statistics); **WP7** high interdependence (provenance ← routing attempts; grounding ← citation checks; interviews ← memory + eligibility + budgeting).

Compute footprint: no LLM training ever, reuse of already-provisioned free capacity, a 3B local model on a 4 GB laptop GPU, a 44-second CPU training run for the persona model — engineering thrift, not a measured carbon claim.

---

## 15. Honest limitations (say them before the judges find them)

1. **The ML model selects, it does not invent.** Personas are whole synthetic source profiles (100 % exact reuse by design). No novel identities, no predicted incomes/budgets/personality scores, no learned purchasing behavior.
2. **It underperforms the lexical baseline** on the held-out retrieval proxy (MRR 0.433 vs 0.752) — reported, not hidden; next experiment planned.
3. **USA-only synthetic corpus.** No validated fit for Bangladesh, students, or any real population; source occupation/location are kept and a mismatch warning is attached. 72/160 probe selections were "not in workforce" (selection bias). Pain points are regex-derived weak labels.
4. **No real business-labelled evaluation exists yet**; retrieval proxies are not customer demand or business relevance.
5. **Default research corpus is illustrative**; only the World Bank adapter is live. Default embeddings are deterministic hashes, not semantic (upgradeable via `embedding_space`).
6. **`OBSERVED` means "verifiably cited", not "semantically entailed"** — entailment checking is roadmap.
7. **Scale is unvalidated**: process-local jobs/rate limits; sequential source exclusions do not lock against concurrent overlapping requests; the historical "~100 personas/day" was an LLM-era target.
8. **Free-tier latency is real** for chat/interviews/reports (seconds to minutes); the UI shows progress and provenance rather than hiding it.
9. **Deployment needs the artifact**: not bundled in a fresh checkout/image; exact NumPy/SciPy/scikit-learn versions required; restart after replacing it.
10. **UI**: mobile persona-header clipping remains; payments are scaffolding (real Stripe endpoints, no live keys, no gating); no admin role; advisory typecheck debt in CI.

---

## 16. Judge Q&A — prepared answers

### Product
- **"What's novel here?"** Two things: treating free-tier chaos as an engineering substrate — a policy router with honest provenance that makes ~20 unreliable free endpoints behave like one reliable API — and code-enforced claim provenance for synthetic research, with a separate trained model owning persona generation.
- **"Who is this for?"** Zero-budget founders and student teams who need to rehearse and de-risk research before spending money on real users. It complements, never replaces, real customers.
- **"Total AI spend?"** $0. Free tiers used legitimately, plus a local GPU fallback; the quota ledger proves consumption stays inside published caps.
- **"Why not GPT-4 + one API key?"** No budget — and no story. The research question is whether routing can *replace* the paid tier; a paid key deletes the thesis.

### LLM / chat layer
- **"How do you get reliability from unreliable free providers?"** 18 task types → 7 pools → quota-aware ranked candidates → per-failure-kind policies (retry once / next / cooldown) → cross-adapter fallback ending on a local model; persistent cooldowns, latency seeding, per-pool concurrency caps; every attempt logged.
- **"What if a provider dies mid-demo?"** The router advances to the next candidate before the first token; after the first token the stream is committed and the failure is shown honestly. Local Ollama is the last resort. Persona generation is unaffected (local ML).
- **"Why refuse to truncate context?"** For this product, context *is* the product; silently dropping identity/evidence yields confident garbage. The only legal adaptation is a bigger-context model; otherwise an explicit error (R2).
- **"Why is bad answer quality not a failure?"** Infra failures are objective and machine-detectable; quality is a judgment. Mixing them would burn quota re-asking questions and make provenance lie. Quality is measured in the evaluation layer (persona evaluator, AI review, local-model gate).
- **"Why a local 3B model first for conversations?"** A judged gate scored it 9.65/9.05/9.2 vs 8.25/8.05/8.2 for the cloud-fast route at ~5–7 s/turn (small sample); heavy generation stays cloud-first. It also keeps the demo alive offline.
- **"How do you know which model actually answered?"** The freellmpool adapter resolves virtual routes to the concrete provider/model; the provenance record and the UI route disclosure show it.

### Persona ML model
- **"Did you train a model? Is it just prompting?"** Yes, a real model: TF-IDF vocabulary/IDF weights + 32-topic NMF fitted on 2,516 training profiles, selected on 539 validation profiles, tested once on 539 held-out profiles; serialized artifacts with integrity checks; 298 tests. No LLM is involved in persona generation — the API returns 503 if the artifact is missing rather than falling back to an LLM.
- **"What type of model and why?"** A specialized retrieval/selection model (bag-of-words + topic factorization + maximal-marginal-relevance selection). Chosen because the task is "pick coherent, diverse, business-relevant profiles from an approved corpus"; it runs on CPU in ~33 ms, is auditable, and preserves internal consistency by never splicing attributes across identities.
- **"Why not generate brand-new personas?"** A bag-of-words model cannot write coherent biographies, and mixing attributes across people creates contradictions. Whole-profile selection keeps each persona internally consistent; the LLM brings the persona to life only in interviews, in character, with the profile as an immutable identity card.
- **"Why not fine-tune an LLM?"** Rule R9 forbids it; no GPU budget (4 GB VRAM); licensing and reproducibility; and fine-tuning would blur the honesty boundary between what was learned and what was invented.
- **"What data? License?"** NVIDIA Nemotron-Personas-USA, CC-BY-4.0, pinned revision, one shard scanned, 6,000 profiles selected deterministically by hash; attribution retained. Researched and rejected: PersonaHub (NC-SA), Synthetic-Persona-Chat (no demographics), UCI restaurant data (real people).
- **"How was it evaluated?"** Held-out cross-view retrieval (rank 539 candidates; MRR/Recall@k) against random, frequency and lexical baselines; structural generation probes (validity, duplicates, diversity 0.878, age JS 0.030, latency); plus backend contract tests and a live end-to-end run. Honest result: the blend loses to plain TF-IDF; we report it.
- **"Why USA data for a Bangladesh product?"** It was the only license-clean, structured, synthetic, demographically grounded corpus found. The pipeline is source-agnostic — adding a Bangladesh source is a manifest entry, a license check and a retrain — and every persona carries its source geography and a mismatch warning.
- **"How do you ensure diversity?"** MMR-style selection: each pick is penalized by its maximum similarity to already-selected profiles (weight 0.25), plus hard exclusion of source identities already active for that owner/study, so five personas are five different people.
- **"Is the persona data private or real?"** Fully synthetic public data; explicit sex/zip/marital fields dropped at ingestion; protected fields excluded from model features; e-mail/URL-bearing rows rejected; user uploads and private studies are never training inputs.

### Honesty / evidence
- **"How do you stop the AI making things up?"** We cannot stop generation from inventing — we stop inventions from being labelled facts: citation verification in code, downgrade-only provenance, grounding score = verified ratio, honest "no evidence" prompts, `SYNTHETIC` labels on every ML persona claim, `CACHED` on demo content.
- **"How do personas stay consistent over long interviews?"** Immutable identity card (byte-identical per turn, test-enforced) + full untruncated history + memory retrieval + numeric-consistency guards + explicit failure if the context cannot fit.

### Engineering
- **"How do you test something built on nondeterministic LLMs?"** Separate layers: routing chaos tests with fake providers (429/timeout/context/all-fail), ML integrity/selection/schema tests with fixture corpora, backend contract tests on SQLite, real-DB integration tests, and live smoke runs recorded as evidence — 1,287 + 298 + 269 tests, CI on Ubuntu.
- **"Why no Kubernetes/Redis/queue?"** Dev-scale honesty (rule R10): asyncio jobs with output persistence give the same 202 + poll UX with zero moving parts; each heavy component was rejected in writing with the trigger that would justify it.
- **"Multi-user? Security?"** JWT auth, server-side federated identity, per-row tenancy with 404-not-403, rate limiting, SSRF-guarded ingestion, prompt-injection isolation, secret hygiene at boot, secret scanning in CI.
- **"Biggest engineering challenge?"** Making failure honest: a closed failure taxonomy that keeps quality out, proven by chaos tests — and later, making a real ML model own persona generation without breaking any existing contract.
- **"What would you build next?"** A pure TF-IDF + diversity selector compared on validation; a business-labelled relevance evaluation; a Bangladesh synthetic source; live search provider; pinned semantic embeddings; entailment checks for `OBSERVED`; concurrency-safe identity locks; the mobile header fix.

---

## 17. Numbers cheat sheet

| Fact | Value |
| --- | --- |
| Task types / pools / failure kinds | 18 / 7 / 13 |
| Free providers via freellmpool | ~18 (library catalogue) + OpenRouter free tier (20/min, 50/day) + Ollama local |
| Local models | `llama3.2:3b` (primary), `qwen3:4b` (secondary), RTX 3050 4 GB |
| Local interview gate | 9.65 / 9.05 / 9.2 vs cloud-fast 8.25 / 8.05 / 8.2 (n = 1 persona × 5 questions) |
| Memory scoring | 0.60 cosine + 0.25 recency (48 h half-life) + 0.15 importance; 384-dim; HNSW |
| ML dataset | Nemotron-Personas-USA, CC-BY-4.0, rev `5b4cd35a…`; 6,000 of 90,910 shard rows; 244 MB shard |
| ML data pipeline | 6,000 → 4,694 valid → 3,594 complete unique → 2,516 / 539 / 539 |
| ML model | TF-IDF 8,000 features + NMF 32 topics; score = 0.7 lexical + 0.3 topic; diversity 0.25; temperature 0.03; seed 42 |
| Training time / hardware | 43.7 s for 4 fits, 2 CPU threads, no GPU |
| Test MRR | model 0.433 · lexical 0.752 · random 0.013 · popularity 0.012 |
| Generation probe | 160/160 structurally valid, diversity 0.878, age JS 0.030, 72/160 not_in_workforce |
| Inference latency | ~33 ms mean, 34.3 ms p95 per 5 personas (warm, CPU) |
| Artifact | ~32.5 MiB, JSON + NPZ, `allow_pickle=False`, version `7eb2fa6f…` |
| Tests | 1,287 backend (81.6 % cov) · 298 ML (97 %) · 269 frontend |
| Endpoints / tables | ~117 / 30+ |
| Live check | 5 unique personas, 22 synthetic attributes, 0 LLM generation calls; 7 real Freellmpool responses via `llm7/codestral-latest` |

---

## 18. Glossary

- **Persona** — a synthetic customer profile (identity, goals, pain points, behaviors) used as an interview/simulation subject.
- **Provenance class** — `OBSERVED` (cites shown evidence), `INFERRED` (reasoned), `SYNTHETIC` (invented/selected; all ML persona claims).
- **Provenance record** — the per-LLM-request audit entry (routing path, attempts, serving model, tokens, latency).
- **Pool** — an ordered list of adapters with a concurrency cap serving a set of task types.
- **Cooldown** — temporarily removing a route after rate-limit/server errors.
- **ContextWindowExceeded** — the explicit error raised instead of truncating context.
- **TF-IDF** — term-frequency × inverse-document-frequency word weighting; **NMF** — non-negative matrix factorization into latent topics; **MRR** — mean reciprocal rank of the correct item; **MMR** — maximal marginal relevance (relevance minus redundancy) for diverse selection; **Jensen-Shannon divergence** — a bounded distance between two distributions.
- **pgvector / HNSW** — Postgres vector extension and its approximate-nearest-neighbour index.
- **freellmpool** — the MIT-licensed library that aggregates free LLM providers with failover and circuit breakers.
- **CACHED** — UI badge for demo/fixture content; never passed off as live AI output.

---

## 19. Where to look in the code (demo map)

| To show… | Open… |
| --- | --- |
| The single LLM entry point + fallback loop | `apps/backend/bebshax/llm/service.py`, `router.py` |
| Pools and task mapping as data | `apps/backend/bebshax/llm/pools.py` |
| Failure taxonomy + policies | `apps/backend/bebshax/llm/failures.py` |
| Provenance record | `apps/backend/bebshax/llm/provenance.py` |
| Citation verification (honesty core) | `coerce_provenance` in `apps/backend/bebshax/persona/schema.py` |
| ML model (fit / score / select / save / load) | `ml_persona/src/bebshax_persona_ml/model.py` |
| ML data normalization and splits | `ml_persona/src/bebshax_persona_ml/data.py` |
| ML lifecycle (prepare / validate / train / evaluate) | `ml_persona/src/bebshax_persona_ml/pipeline.py`, `evaluation.py`, `cli.py` |
| ML → backend boundary | `apps/backend/bebshax/personas/ml_adapter.py` |
| Interview context composition | `_compose` in `apps/backend/bebshax/interview/engine.py` |
| Memory scoring | `apps/backend/bebshax/memory/service.py` |
| Judge Lab failure drills | `apps/backend/bebshax/api/demo_lab.py` |
| Study workflow UI | `apps/frontend/src/components/dashboard/views/StudyWorkflowView.tsx` + `workflow/Step1…Step5` |

Deeper documents: `FINAL_IMPLEMENTATION_REPORT.md`, `SUMMARY.md` (long showcase guide), `docs/ARCHITECTURE.md`, `docs/ROUTING.md`, `docs/FAILOVER.md`, `docs/PERSONA_ENGINE.md`, `docs/EVALUATION.md`, `docs/DEMO.md`, `docs/API_CONTRACT.md`, `docs/JUDGE_QA.md`, `ml_persona/README.md`, `ml_persona/MODEL_CARD.md`, `ml_persona/EXPERIMENTS.md`, `ml_persona/DATASETS.md`, `ml_persona/IMPLEMENTATION_REPORT.md`, and the build history in `docs/IMPLEMENTATION_PLAN.md`.
