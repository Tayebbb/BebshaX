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
| 11 | Quality/evaluation | persona validity/consistency/grounding scoring; routing strategies behind config (ROUND_ROBIN / LEAST_USED / QUALITY_FIRST / LATENCY_FIRST / CAPABILITY_FIRST / QUOTA_AWARE / HYBRID default); RouterArena + xRouteBench offline comparison | one-command eval report; naive-vs-intelligent routing table |
| 12 | Frontend | React + Vite app: business setup, persona generation, profiles, memory view, interview/simulation, insights, routing dashboard, provider status, fallback history, provenance, eval metrics | all views wired to the API |
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

### Phase 1 — Foundation (2026-08-22) ✅
- Repo initialized; scaffold: `apps/backend` (package `bebshax`), `data/{raw,processed,metadata}`, `docker-compose.yml`, `.env.example`, `.gitignore`, `README.md`.
- Config: pydantic-settings with `BEBSHAX_` prefix. Provider keys deliberately NOT modeled in `Settings` — freellmpool reads standard env vars directly, keeping the provider list configuration-driven (owner decision #10).
- Dependencies added (all permissive-licensed, actively maintained, minimal set): `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`; dev-only: `pytest`, `pytest-asyncio`, `httpx`. Exact versions snapshotted in `apps/backend/requirements.lock`.
- **Finding:** native PostgreSQL 16 lacks pgvector (`vector.control` absent) → app DB is `pgvector/pgvector:pg16` on port **5433** (native keeps 5432). Compose file validated with `docker compose config`; container start deferred to Phase 6.
- Verified: 3/3 tests green; live `GET /api/health` → 200 `{"status":"ok","app":"BebshaX","version":"0.1.0",...}`.
- Known item: starlette TestClient emits a deprecation warning suggesting `httpx2`; revisit when starlette requires it.
- Deviation from earlier draft: 22-phase plan replaced by the owner's 15-phase structure (recorded above).
