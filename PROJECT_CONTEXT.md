# BebshaX — Project Context (single source of truth)

> Read this first. If any other document contradicts this file, this file wins — fix the other one.
> Renamed from _SignalLens_ on 2026-08-22; the old name appears only in rename notes.

## What we are building

BebshaX is a synthetic-user / persona research system: a trained CPU-only model selects coherent **synthetic source personas** for a business/product context and lets those personas participate in **interviews and simulations**. Persona selection is independent of LLMs; conversation/research features use **legitimately accessed free LLM capacity** behind governed routing and failover, with local Ollama available as a fallback. Source profiles are hypotheses, not observed customers or validated demand.

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
   FreellmpoolAdapter → freellmpool (MIT) → 18 providers in the freellmpool 0.11.4 catalog (verified 2026-08-28) / keyless start
   OllamaAdapter      → local Ollama (final reliability fallback)
        │
PostgreSQL 16 + pgvector (Docker, port 5433) — personas, evidence, memory,
   llm_requests (provenance), model_registry
```

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
hints, and income/OCEAN values stay unknown. Sequential owner-scoped identity
exclusions do not provide a concurrent transactional uniqueness lock.

Recorded continuation checks passed offline suites, local PostgreSQL
persistence/pgvector, seven real Freellmpool responses, and Windows-artifact
loading in the Linux backend image with networking disabled. Desktop passed;
mobile persona-header clipping remains. These are scoped checks, not a provider
success rate or production verdict. Full Compose app/web rehearsal,
cross-conversation memory retrieval, and final post-sync publication gates are
not claimed complete; see the [ML report](ml_persona/IMPLEMENTATION_REPORT.md).
This addendum does not change the original phase roadmap or completion dates.

## Stack (decided — do not relitigate casually)

| Layer          | Choice                                                                                                                        | Why                                                    |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| Backend        | Python 3.12 + FastAPI, async                                                                                                  | freellmpool is Python; best dataset/eval ecosystem     |
| Routing engine | freellmpool as a **library** behind `LLMService`                                                                              | MIT, active, failover/quotas/circuits/keyless built in |
| LiteLLM        | Not installed (Gate B, revisit only if a provider is missing)                                                                 | avoids heavy proxy stack                               |
| DB             | PG16 + pgvector via `pgvector/pgvector:pg16` on **5433**                                                                      | native PG16 on the dev machine lacks pgvector          |
| Local fallback | Ollama — `llama3.2:3b` primary / `qwen3:4b` secondary (Phase 4 benchmark)                                                     | 4 GB VRAM ceiling — no 70B fantasies                   |
| Frontend       | React + Vite, single app                                                                                                      | owner decision                                         |
| Persona model  | CPU TF-IDF/NMF representations + diversity-aware synthetic source selection | Separate from LLM routing; source identity/provenance retained |
| Datasets       | Existing profiles: grounding + evaluation only; separate `ml_persona` profile for explicitly reviewed synthetic training data | **no LLM fine-tuning, ever**                           |

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

| Question                                 | Document                                                                                                 |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| What is this project / current state?    | **this file**                                                                                            |
| What must every AI agent/tool obey?      | [AGENTS.md](AGENTS.md) (auto-loaded by Copilot/Cursor/Claude Code/Codex)                                 |
| What are the engineering rules?          | [RULES.md](RULES.md)                                                                                     |
| What exactly is phase N?                 | [docs/PHASES.md](docs/PHASES.md) (executable specs)                                                      |
| Who works on what, without collisions?   | [docs/TEAM_ASSIGNMENTS.md](docs/TEAM_ASSIGNMENTS.md)                                                     |
| How do I set up my machine?              | [docs/TEAM_SETUP.md](docs/TEAM_SETUP.md)                                                                 |
| What's the plan / what changed?          | [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) (implementation log at the bottom)            |
| Why these OSS choices / hardware limits? | [docs/AI_INFRASTRUCTURE_AUDIT.md](docs/AI_INFRASTRUCTURE_AUDIT.md)                                       |
| How does the LLM actually work here?     | [docs/AI_IMPLEMENTATION_PLAN.md](docs/AI_IMPLEMENTATION_PLAN.md) (routing vs aggregation, plain-English) |
| How are personas trained and selected now? | [ml_persona/README.md](ml_persona/README.md), [model card](ml_persona/MODEL_CARD.md), [application adapter](docs/PERSONA_ENGINE.md) |
| How does routing work / provider config? | [docs/ROUTING.md](docs/ROUTING.md)                                                                       |
| Who fixes which audit finding?           | [docs/AUDIT_ASSIGNMENTS.md](docs/AUDIT_ASSIGNMENTS.md)                                                   |
