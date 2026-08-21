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
