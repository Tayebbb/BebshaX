# BebshaX — Project Context (single source of truth)

> Read this first. If any other document contradicts this file, this file wins — fix the other one.
> Renamed from _SignalLens_ on 2026-08-22; the old name appears only in rename notes.

## What we are building

BebshaX is a synthetic-user / persona research system: a trained CPU-only model selects coherent **synthetic source personas** for a business/product context and lets those personas participate in **interviews and simulations**. Persona selection is independent of LLMs; conversation/research features use **legitimately accessed free LLM capacity** behind governed routing and failover. The owner-approved remote-only policy uses Freellmpool as the primary tier and independent OpenRouter as the secondary tier. Source profiles are hypotheses, not observed customers or validated demand.

**Research question:** _Can intelligent multi-model routing aggregate free LLM capacity while preserving synthetic persona quality and user experience?_

## Non-negotiable principles

1. **Quality is never silently degraded.** No truncating persona context to fit a weaker model, no swapping identity, no hidden fallbacks. If a request cannot be served with sufficient context/capability → **explicit failure** (`ContextWindowExceeded`, `AllCandidatesFailed`).
2. **Low answer quality is NOT an infrastructure failure.** Infra fallback handles 429/quota/timeouts/5xx/context/capability errors only. Quality belongs to the evaluation layer (Phase 11).
3. **Legitimate free-tier use only.** No fake/duplicate accounts, no rate-limit evasion, no leaked keys. Teammates add their own legitimately-owned keys via environment variables.
4. **One AI system.** End users click "Generate Persona" — they never pick model #73. Routing is the backend's job; the developer dashboard exposes it for us, not for them.
5. **Existing OSS → thin adapter → custom BebshaX logic.** We do not rebuild routers, gateways, or ORMs. Custom code = personas, memory, evidence, interviews, quality, routing _policy_, provenance, evaluation, UI.

## Architecture

```
React + Vite frontend (apps/frontend — Phase 12)
        │ REST
FastAPI backend (apps/backend, package `bebshax`, Python 3.12, async)
        │
        ├─ Persona generation (business / study / roles / datasets)
        │    MLPersonaAdapter → CPU TF-IDF/NMF + source selection
        │    → existing persona schemas / synthetic provenance / storage
        │
bebshax.llm — existing LLM policy for copilot, interviews, research, reports
   LLMService ← the ONLY entry point for LLM calls (takes a TaskType)
   task → pool → eligible candidates → ranked → attempt → classified failure → fallback
   pre-flight context budgeting · per-pool concurrency · full provenance per request
        │
bebshax.llm.adapters — the ONLY code allowed to import provider SDKs
        FreellmpoolAdapter → policy-approved remote providers (primary)
        OpenRouterAdapter → independently configured free remote models (secondary)
        │
PostgreSQL 16 + pgvector (Docker, port 5433) — personas, evidence, memory,
   llm_requests (provenance), model_registry
```

### Post-Presentation Modernization (2026-09-09)

The owner approved the full [modernization roadmap](docs/POST_PRESENTATION_ROADMAP.md)
and its quality-preserving latency contract. Implementation and integration are
in progress; [the execution ledger](docs/MODERNIZATION_EXECUTION.md) records the
actual verification scope. Older completion/readiness entries below remain
historical evidence, not current production certification.

Production pool tables now contain only Freellmpool then OpenRouter. Local and
cloud Ollama are excluded from the target runtime, including embedding discovery;
hash-based local embeddings are a separate non-Ollama component. Historical
Ollama provenance and benchmark records are retained. Remaining tooling, docs,
configuration and migration compatibility are part of the integration gates.
There is no offline live-inference guarantee. No provider policy may evade
quotas, truncate context, silently weaken output or disclose private content
to unapproved destinations. Every page must be measured against the roadmap's
latency budgets separately from genuine AI text and durably saved completion.

### Current ML Addendum (2026-09-09)

Persona generation now shares the isolated [Persona ML](ml_persona/README.md)
CPU TF-IDF/NMF selector across business, study, role, and dataset paths, mapped
to existing schemas/storage. Local training and evaluation are complete; selected
source bundles and claims remain `SYNTHETIC`, not observed customer evidence.
This path needs no LLM, API key, GPU, or PyTorch and never falls back to an LLM;
chat/interviews still use the router above. The default ignored artifact is
`data/processed/ml_persona/model`, with `BEBSHAX_ML_PERSONA_ARTIFACT_DIR` override.
Fresh installs must prepare/train or stage a trusted compatible bundle; numerical
versions are pinned in [ml_persona/constraints.txt](ml_persona/constraints.txt),
also used by Docker. Model loading is cached; restart after replacement.
Unavailable models return 503, unsupported/exhausted selections 422.

The [model card](ml_persona/MODEL_CARD.md) records lower held-out retrieval MRR
than lexical TF-IDF (0.432654 versus 0.751621), USA-synthetic-only coverage,
and no validated population/student/Bangladesh fit. Source occupation/location
is retained; explicit ages in 18–95 are hard constraints, role/location are soft
hints, and income/OCEAN values stay unknown. Source exclusions now use cooperating
study/business/dataset parent-row locks before selection and persistence;
regeneration archives old rows under lock. There is no global source-identity
unique constraint. SQLite FK tests and PostgreSQL-compiled SQL checks do not
prove live PostgreSQL multi-process concurrency.

The [post-sync local checks](ml_persona/IMPLEMENTATION_REPORT.md#post-sync-verification-2026-09-09)
passed at the documented scopes. Earlier checks passed local PostgreSQL
persistence/pgvector, seven real Freellmpool responses, and Windows-artifact
loading in Linux with networking disabled. Desktop passed before upstream
styling; mobile persona-header clipping remains unfixed and was not reverified
after the upstream changes or approved token-only correction. These are scoped
checks, not a provider success rate or production verdict. Full Compose app/web
and cross-conversation memory retrieval rehearsals were not repeated. Commit,
push, and CI results are tracked separately in the
[implementation log](docs/IMPLEMENTATION_PLAN.md), not claimed successful here.
This addendum does not change the original phase roadmap or completion dates.

### Current Hardening Status (2026-09-09)

**READY WITH RESERVATIONS**, not production sign-off. Parent-reported current
checks: backend 1,639 passed / 3 integration deselected (773.82 s, 82.72% coverage,
80% required); frontend 293 tests / 40 files, TypeScript/Vite PASS (4.39 s),
theme check 0 files; ML 298 passed (34.05 s); root SSRF regression 3 passed.
All five backend-enabled ML smoke stages passed with five profiles. Dependency
consistency, full-profile Compose configuration, and changed-Python bug-tier Ruff
passed. The initial 11 backend failures are resolved; no test failures remain
in these reported runs. The ML model remains frozen; no LLM fine-tuning.

Current hardening covers shared batch-job admission/ownership, transcript
hydration, selected/latest segmentation, atomic persona deletion and snapshots,
complete observed-group statistics and validated count-based quotas, full-fidelity
report context with atomic versions, and frontend request-epoch/navigation/restore
guards. Independent reviews of batch ownership/admission, transcript hydration,
and statistics/quotas were code-only.

Built-preview checks at desktop 1440x1000 loaded all visible images; mobile
390x844 checked navigation, keyboard, theme, sign-in input labels, and no horizontal
overflow. These do not establish an authenticated critical journey or resolution
of the earlier persona-header finding. Health returned HTTP 200 in 20/20 samples:
p50 717.2 ms, p95 1195.3 ms, p99 1761.1 ms during ML tests, not a clean baseline.
The current Freellmpool smoke failed and is under diagnosis; two real copilot
HTTP 200 responses (6.06 s, 2.73 s) belong to another concurrent workstream,
not this run. Neither observation establishes fleet-wide provider availability.

Remaining gates: real 50-turn conversation, PostgreSQL full-stack/concurrency,
offline-provider and real-user rehearsals, real Google sign-in/checkout, and
verification of historical credential rotation. No commit, push, or CI success
is claimed. Detailed current evidence: [ship readiness](docs/SHIP_READINESS_REPORT.md).

## Stack (decided — do not relitigate casually)

| Layer          | Choice                                                                                                                        | Why                                                            |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| Backend        | Python 3.12 + FastAPI, async                                                                                                  | freellmpool is Python; best dataset/eval ecosystem             |
| Routing engine | freellmpool as a **library** behind `LLMService`                                                                              | MIT, active, failover/quotas/circuits/keyless built in         |
| LiteLLM        | Not installed (Gate B, revisit only if a provider is missing)                                                                 | avoids heavy proxy stack                                       |
| DB             | PG16 + pgvector via `pgvector/pgvector:pg16` on **5433**                                                                      | native PG16 on the dev machine lacks pgvector                  |
| Local fallback | Ollama — `llama3.2:3b` primary / `qwen3:4b` secondary (Phase 4 benchmark)                                                     | 4 GB VRAM ceiling — no 70B fantasies                           |
| Frontend       | React + Vite, single app                                                                                                      | owner decision                                                 |
| Persona model  | CPU TF-IDF/NMF representations + diversity-aware synthetic source selection                                                   | Separate from LLM routing; source identity/provenance retained |
| Datasets       | Existing profiles: grounding + evaluation only; separate `ml_persona` profile for explicitly reviewed synthetic training data | **no LLM fine-tuning, ever**                                   |

## Phase roadmap and status

**15 phases total** (an earlier 22-phase draft was superseded on 2026-08-22 — this table is authoritative). Executable per-phase specs: [docs/PHASES.md](docs/PHASES.md). Who implements what, in parallel: [docs/TEAM_ASSIGNMENTS.md](docs/TEAM_ASSIGNMENTS.md). To execute a phase, tell your AI agent: **"Implement phase N"** (protocol in [AGENTS.md](AGENTS.md)).
| # | Phase | Status |
| --- | ---------------------------------------------------------------------- | -------------- |
| 1 | Foundation (scaffold, config, health, tests, compose) | ✅ 2026-08-22 |
| 2 | LLM abstraction (LLMService, task types, failure taxonomy, provenance) | ✅ 2026-08-22 |
| 3 | freellmpool integration (adapter, keyless smoke, Gate B) | ✅ 2026-08-22 |
| 4 | Ollama integration (benchmark qwen3.5 first) | ✅ 2026-08-22 |
| 5 | Routing/fallback (pools, ranking, context budget, concurrency) | ✅ 2026-08-22 |
| 6 | Database (Alembic; model_registry, llm_requests, personas) | ✅ 2026-08-22 |
| 7 | Dataset pipeline (profiles, one-command reproducible) | ✅ 2026-08-22 |
| 8 | Persona engine | ✅ 2026-08-23 |
| 9 | Memory (pgvector stream: relevance+recency+importance) | ✅ 2026-08-23 |
| 10 | Interview engine | ✅ 2026-08-23 |
| 11 | Quality/evaluation (+ routing strategy experiments) | ✅ 2026-08-22 |
| 12 | Frontend (Foundation & Views on mocks) | ✅ 2026-08-22 |
| 13 | Integration + demo mode | ✅ 2026-08-28 (flag-gated seeding, cached labeling end-to-end, DEMO.md walkthrough + offline drill) |
| 14 | Testing (full matrix + acceptance tests) | ✅ 2026-08-28 |
| 15 | Documentation | ✅ 2026-08-28 |

Detailed deliverables/exit criteria: [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md). Environment/ecosystem audit: [docs/AI_INFRASTRUCTURE_AUDIT.md](docs/AI_INFRASTRUCTURE_AUDIT.md).

## Key decisions record

| ID  | Decision                                                                                                                                                                                                             | Where detailed              |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------- |
| D1  | freellmpool is the routing engine, used as a library                                                                                                                                                                 | audit §6.2, docs/ROUTING.md |
| D2  | Provider SDKs importable ONLY inside `bebshax/llm/adapters/` (test-enforced)                                                                                                                                         | RULES.md R1                 |
| D3  | Quality excluded from the failure taxonomy (test-enforced)                                                                                                                                                           | `bebshax/llm/failures.py`   |
| D4  | App DB = pgvector Docker container on port 5433                                                                                                                                                                      | docker-compose.yml          |
| D5  | Providers/keys are env-config only — never hard-coded                                                                                                                                                                | .env.example                |
| D6  | Existing datasets remain grounding/eval only. Owner-approved 2026-09-08 exception: reviewed, explicitly training-allowed public synthetic datasets may train the isolated non-LLM persona model. No LLM fine-tuning. | ml_persona/ARCHITECTURE.md  |
| D7  | 18 fixed task types (16 + PERSONA_NARRATIVE/BEHAVIORAL_SIMULATION, 2026-08-26); callers declare them; no LLM-based classification                                                                                    | `bebshax/llm/types.py`      |
| D8  | Every LLM request records full provenance (§14 fields)                                                                                                                                                               | `bebshax/llm/provenance.py` |

## Document map

| Question                                   | Document                                                                                                                            |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| What is this project / current state?      | **this file**                                                                                                                       |
| What must every AI agent/tool obey?        | [AGENTS.md](AGENTS.md) (auto-loaded by Copilot/Cursor/Claude Code/Codex)                                                            |
| What are the engineering rules?            | [RULES.md](RULES.md)                                                                                                                |
| What exactly is phase N?                   | [docs/PHASES.md](docs/PHASES.md) (executable specs)                                                                                 |
| Who works on what, without collisions?     | [docs/TEAM_ASSIGNMENTS.md](docs/TEAM_ASSIGNMENTS.md)                                                                                |
| How do I set up my machine?                | [docs/TEAM_SETUP.md](docs/TEAM_SETUP.md)                                                                                            |
| What's the plan / what changed?            | [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) (implementation log at the bottom)                                       |
| Why these OSS choices / hardware limits?   | [docs/AI_INFRASTRUCTURE_AUDIT.md](docs/AI_INFRASTRUCTURE_AUDIT.md)                                                                  |
| How does the LLM actually work here?       | [docs/AI_IMPLEMENTATION_PLAN.md](docs/AI_IMPLEMENTATION_PLAN.md) (routing vs aggregation, plain-English)                            |
| How are personas trained and selected now? | [ml_persona/README.md](ml_persona/README.md), [model card](ml_persona/MODEL_CARD.md), [application adapter](docs/PERSONA_ENGINE.md) |
| How does routing work / provider config?   | [docs/ROUTING.md](docs/ROUTING.md)                                                                                                  |
| Who fixes which audit finding?             | [docs/AUDIT_ASSIGNMENTS.md](docs/AUDIT_ASSIGNMENTS.md)                                                                              |
