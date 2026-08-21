# BebshaX — Project Context (single source of truth)

> Read this first. If any other document contradicts this file, this file wins — fix the other one.
> Renamed from _SignalLens_ on 2026-08-22; the old name appears only in rename notes.

## What we are building

BebshaX is a synthetic-user / persona research system: it generates realistic, **evidence-grounded personas** for a specific business/product and lets those personas participate in **interviews and simulations**. Because the project has essentially **zero API budget**, all intelligence runs on **legitimately accessed free LLM capacity**, aggregated behind intelligent routing, failover, and context-aware model selection — with a local Ollama model as the final reliability fallback.

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
bebshax.llm — BebshaX policy layer (custom)
   LLMService ← the ONLY entry point for LLM calls (takes a TaskType)
   task → pool → eligible candidates → ranked → attempt → classified failure → fallback
   pre-flight context budgeting · per-pool concurrency · full provenance per request
        │
bebshax.llm.adapters — the ONLY code allowed to import provider SDKs
   FreellmpoolAdapter → freellmpool (MIT) → ~24 free providers / 222 routes / keyless start
   OllamaAdapter      → local Ollama (final reliability fallback)
        │
PostgreSQL 16 + pgvector (Docker, port 5433) — personas, evidence, memory,
   llm_requests (provenance), model_registry
```

## Stack (decided — do not relitigate casually)

| Layer          | Choice                                                                     | Why                                                    |
| -------------- | -------------------------------------------------------------------------- | ------------------------------------------------------ |
| Backend        | Python 3.12 + FastAPI, async                                               | freellmpool is Python; best dataset/eval ecosystem     |
| Routing engine | freellmpool as a **library** behind `LLMService`                           | MIT, active, failover/quotas/circuits/keyless built in |
| LiteLLM        | Not installed (Gate B, revisit only if a provider is missing)              | avoids heavy proxy stack                               |
| DB             | PG16 + pgvector via `pgvector/pgvector:pg16` on **5433**                   | native PG16 on the dev machine lacks pgvector          |
| Local fallback | Ollama (`qwen3.5:latest` now; ≤4 GB-VRAM fast model chosen in Phase 4)     | 4 GB VRAM ceiling — no 70B fantasies                   |
| Frontend       | React + Vite, single app                                                   | owner decision                                         |
| Datasets       | Profiles: minimal/development/evaluation/full; grounding + evaluation only | **no fine-tuning, ever**                               |

## Phase roadmap and status
**15 phases total** (an earlier 22-phase draft was superseded on 2026-08-22 — this table is authoritative). Executable per-phase specs: [docs/PHASES.md](docs/PHASES.md). Who implements what, in parallel: [docs/TEAM_ASSIGNMENTS.md](docs/TEAM_ASSIGNMENTS.md). To execute a phase, tell your AI agent: **"Implement phase N"** (protocol in [AGENTS.md](AGENTS.md)).
| #   | Phase                                                                  | Status         |
| --- | ---------------------------------------------------------------------- | -------------- |
| 1   | Foundation (scaffold, config, health, tests, compose)                  | ✅ 2026-08-22  |
| 2   | LLM abstraction (LLMService, task types, failure taxonomy, provenance) | ✅ 2026-08-22  |
| 3   | freellmpool integration (adapter, keyless smoke, Gate B)               | ✅ 2026-08-22 |
| 4   | Ollama integration (benchmark qwen3.5 first)                           | ✅ 2026-08-22  |
| 5   | Routing/fallback (pools, ranking, context budget, concurrency)         | ✅ 2026-08-22  |
| 6   | Database (Alembic; model_registry, llm_requests, personas)             | ✅ 2026-08-22 |
| 7   | Dataset pipeline (profiles, one-command reproducible)                  | ⬜             |
| 8   | Persona engine                                                         | ⬜             |
| 9   | Memory (pgvector stream: relevance+recency+importance)                 | ⬜             |
| 10  | Interview engine                                                       | ⬜             |
| 11  | Quality/evaluation (+ routing strategy experiments)                    | ⬜             |
| 12  | Frontend                                                               | ⬜             |
| 13  | Integration + demo mode                                                | ⬜             |
| 14  | Testing (full matrix + acceptance tests)                               | ⬜             |
| 15  | Documentation                                                          | ⬜             |

Detailed deliverables/exit criteria: [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md). Environment/ecosystem audit: [docs/AI_INFRASTRUCTURE_AUDIT.md](docs/AI_INFRASTRUCTURE_AUDIT.md).

## Key decisions record

| ID  | Decision                                                                     | Where detailed                        |
| --- | ---------------------------------------------------------------------------- | ------------------------------------- |
| D1  | freellmpool is the routing engine, used as a library                         | audit §6.2, docs/ROUTING.md           |
| D2  | Provider SDKs importable ONLY inside `bebshax/llm/adapters/` (test-enforced) | RULES.md R1                           |
| D3  | Quality excluded from the failure taxonomy (test-enforced)                   | `bebshax/llm/failures.py`             |
| D4  | App DB = pgvector Docker container on port 5433                              | docker-compose.yml                    |
| D5  | Providers/keys are env-config only — never hard-coded                        | .env.example                          |
| D6  | Datasets for grounding/eval only; no model training                          | docs/IMPLEMENTATION_PLAN.md non-goals |
| D7  | 16 fixed task types; callers declare them; no LLM-based classification       | `bebshax/llm/types.py`                |
| D8  | Every LLM request records full provenance (§14 fields)                       | `bebshax/llm/provenance.py`           |

## Document map

| Question                                 | Document                                                                                      |
| ---------------------------------------- | --------------------------------------------------------------------------------------------- |
| What is this project / current state?    | **this file**                                                                                 |
| What must every AI agent/tool obey?      | [AGENTS.md](AGENTS.md) (auto-loaded by Copilot/Cursor/Claude Code/Codex)                      |
| What are the engineering rules?          | [RULES.md](RULES.md)                                                                          |
| What exactly is phase N?                 | [docs/PHASES.md](docs/PHASES.md) (executable specs)                                           |
| Who works on what, without collisions?   | [docs/TEAM_ASSIGNMENTS.md](docs/TEAM_ASSIGNMENTS.md)                                          |
| How do I set up my machine?              | [docs/TEAM_SETUP.md](docs/TEAM_SETUP.md)                                                      |
| What's the plan / what changed?          | [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) (implementation log at the bottom) |
| Why these OSS choices / hardware limits? | [docs/AI_INFRASTRUCTURE_AUDIT.md](docs/AI_INFRASTRUCTURE_AUDIT.md)                            |
| How does routing work / provider config? | [docs/ROUTING.md](docs/ROUTING.md)                                                            |
