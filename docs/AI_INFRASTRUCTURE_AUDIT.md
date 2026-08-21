# BebshaX — AI Infrastructure Audit

Date: 2026-08-22
Phase: 0 (audit only — no implementation performed)
Workspace: `e:\BebshaX`

> Project renamed **SignalLens → BebshaX** by the owner on 2026-08-22 (historical note; the audit below has been updated to the new name).

---

## 0. Executive summary

**The repository is empty.** `e:\BebshaX` contains no source code, no `.git` directory, no hidden files, no configuration. There is no existing frontend, backend, database schema, AI integration, persona system, memory system, dataset, or test suite to audit.

Consequences:

1. Every "inspect existing X" item in the project brief resolves to **N/A — does not exist**.
2. The project is a **greenfield build** — confirmed by the owner on 2026-08-22 (former open question Q1).
3. The upside: nothing constrains the architecture. We can pick the stack that best matches the routing requirements instead of retrofitting one.

The host machine, however, is well prepared: Python 3.12, Node 24, Docker (daemon running), PostgreSQL 16 (service running), and Ollama 0.20 with one 6.6 GB model already pulled.

---

## 1. Current architecture

| Item | Status |
|---|---|
| Frontend | None |
| Backend | None |
| Database (app-level) | None — but PostgreSQL 16 server is installed and running on the host |
| Authentication | None |
| AI integration / LLM calls | None in repo |
| Hard-coded model/provider | None (nothing to hard-code yet) |
| Persona generation / tables | None |
| Interview / conversation system | None |
| Memory system | None |
| Vector DB / search | None (pgvector availability on the local PG 16 not yet verified) |
| Datasets / seed data | None |
| Evaluation infrastructure | None |
| Environment configuration | None (no `.env`, no `.env.example`) |
| Docker configuration | None in repo; Docker Desktop 29.7.2 running on host |
| Tests | None |
| CI | None |

## 2. Current AI flow

None exists. There are zero LLM calls to migrate and zero providers to decouple.

## 3. Existing problems

The only "problem" is absence. There is no legacy code to preserve, no APIs to keep stable, no working functionality to avoid breaking. All constraints in the brief about "do not rewrite working application code" are vacuously satisfied.

## 4. Files to modify / leave untouched

- Files to modify: none exist.
- Files to leave untouched: none exist.
- Everything will be new. The integration-point question becomes an architecture-boundary question (§8).

---

## 5. Host environment audit (hardware + installed software)

### 5.1 Hardware

| Resource | Value | Implication for LLM infra |
|---|---|---|
| CPU | Intel i5-12500H, 12 cores / 16 threads | Fine for API serving, embedding, preprocessing |
| RAM | 15.7 GB total | Hard ceiling on local model size; leave ≥6 GB for OS+services |
| GPU | NVIDIA RTX 3050 Laptop, **4 GB VRAM** (+ Iris Xe iGPU) | Only ~3–4B Q4 models fit fully in VRAM; 7–8B Q4 runs with CPU offload (slower) |
| Disk (E:) | 195 GB free | Plenty for datasets + a few local models |

**Local model policy derived from this:** the Ollama fallback tier must use small models. Recommended profile:
- Fast local fallback: a ~3–4B instruct model (fully GPU-resident, low latency).
- Quality local fallback: the already-pulled `qwen3.5:latest` (6.6 GB, partial CPU offload — works, slower).
- **A 70B model is impossible on this machine. Do not configure one.**

### 5.2 Installed software

| Tool | Version / state | Notes |
|---|---|---|
| Python | 3.12.9 | Meets freellmpool requirement (≥3.11) |
| Node.js | v24.11.1 (npm present, pnpm absent) | Available for frontend |
| Git | Installed | Repo initialized in Phase 1 |
| Docker | 29.7.2, daemon **running** | Compose available |
| PostgreSQL | 16, service **running** (`postgresql-x64-16`) | Native install; **Phase-1 finding: pgvector NOT installed** (`vector.control` absent) → app DB runs as `pgvector/pgvector:pg16` container on port 5433 |
| Ollama | 0.20.0, models: `qwen3.5:latest` (6.6 GB) | Final-fallback tier ready |

---

## 6. Open-source repository evaluation

All 13 repositories from the brief were inspected (README, license, activity, release state) on 2026-08-22.

### 6.1 Verdicts

| Repo | License | Activity | Verdict |
|---|---|---|---|
| **0xzr/freellmpool** | MIT | Active (commits ≤3 weeks old, v0.11.4 on PyPI) | **ADOPT — primary routing engine (as a Python library + local proxy)** |
| **BerriAI/litellm** | MIT (core) | Extremely active, 56.9k★ | **CONDITIONAL** — do not deploy the proxy/gateway (Postgres+Prisma+Redis overhead violates "don't over-engineer"). Permit the SDK as a dispatch dependency only if a needed provider is missing from freellmpool (decision gate, Phase 3) |
| RouteWorks/RouterArena | Apache-2.0 | Active (Rice Univ.) | **REFERENCE + dataset** — evaluation methodology (5 router metrics) and HF eval dataset. Never in production path |
| ulab-uiuc/LLMRouter | MIT | Very active, 2.4k★ | **REFERENCE** — xRouteBench replays pre-recorded model executions ⇒ **zero-API-cost routing evaluation**. Research comparison only; never in production path |
| joonspk-research/generative_agents | Apache-2.0 | Dormant (3 y) | **CONCEPTS ONLY** — memory-stream architecture (observation → retrieval by relevance+recency+importance → reflection). Do not install (Python 3.9 Django-era code) |
| mnfst/awesome-free-llm-apis | CC0 | Auto-refreshed (12 h ago) | **DATA SOURCE** — machine-readable `data.json` of free providers/limits; freellmpool already syncs it as an advisory catalog. Use to seed/refresh model registry |
| NadirRouter/NadirClaw | PolyForm **Noncommercial** 1.0.0 | Active, 642★ | **SKIP as infra** (license OK for a university project but its goal is paid-model cost-saving, not free-pool aggregation; brings sentence-transformer classifier weight). Borrow concepts: verifier-gated cascade, context-window swap |
| shihabshahrier/freelm | MIT | Recent but tiny (2★) | **SKIP** — clean client-side failover over 6 free providers (Py+JS), but a strict subset of freellmpool. Fallback option if freellmpool ever dies |
| tokkkie/free-model-router | MIT | Tiny (1★), 3 mo | **SKIP** — redundant subset (4 providers + Ollama). Nice idea worth copying: startup tool-call verification per model |
| openfreerouter/freerouter | MIT | Stale 6 mo, fork | **SKIP** — 14-dimension complexity classifier for paid tiers; not free-pool oriented. Concept reference only |
| ExeconOne/ollama-agent-router | MIT | 0★, single author | **SKIP** — multi-model local GPU routing; pointless with a single 4 GB GPU |
| lrbmike/APIKeyRotator | MIT | 5★, 7 mo | **SKIP** — key rotation proxy; freellmpool already rotates multiple keys per provider |
| cuihuan/awesome-ai-gateway, yenanjing/awesome-model-routing | list repos | — | **REFERENCE lists** only; no code to adopt |

### 6.2 Why freellmpool is the primary engine

Feature-by-feature match against the brief's hard requirements:

| Brief requirement | freellmpool support |
|---|---|
| Large dynamic pool, config-driven | 24 providers / 222 routes / 407 models cataloged in `providers.toml`; registry not hard-coded in app code |
| Failover chain on 429/5xx/timeout | Yes — per-route circuit breakers, Retry-After honoring, half-open probes |
| Context-window routing, never truncate | Yes — learns per-model limits, skips oversized routes, raises **`ContextWindowExceeded`** (HTTP 413 via proxy). Exactly the semantic §6 of the brief demands |
| Quality-aware routing | `FREELLMPOOL_ROUTING=quality` — benchmark-grounded capability scores (LMArena Elo MIT snapshot + Aider Apache-2.0; optional Artificial Analysis sync) |
| Quota/capacity tracking | Per-key RPM token bucket + per-day counters, UTC reset, `capacity status`, quota-aware "wise" mode |
| Multiple legitimate keys per provider | Supported (comma-separated env keys); explicitly refuses limit-evasion mechanics |
| Health checks | `providers health`, `conformance run` (chat/streaming/tools/JSON/vision probes with bounded synthetic requests) |
| Provenance / observability | `on_event` callback stream (attempt/success/error/cooldown/cache), persisted route health, `/status`, `/dashboard`, Prometheus-ready proxy surfaces |
| Caching | Optional SQLite response cache (TTL, WAL) + model-catalog cache |
| Ollama fallback | First-class provider |
| Keyless start | Pollinations / OVHcloud / Kilo / LLM7 — demo can answer with zero keys configured |
| License / ethics | MIT; README states it does not bypass limits, rotate accounts, or evade quotas |

Gaps freellmpool does **not** cover (⇒ this is exactly the custom BebshaX layer we must build):

1. **Task types** (PERSONA_GENERATION … EMERGENCY_FALLBACK) and task→pool mapping. freellmpool has "roles" and a coarse task hint, not our 16 task types.
2. **Named model pools** (reasoning_pool, conversation_pool, long_context_pool…) with per-pool concurrency semaphores.
3. **Pre-flight token budgeting** across persona identity + memory + evidence + conversation (freellmpool learns limits reactively; the brief demands proactive estimation too).
4. **Provenance persistence** to our own Postgres schema (`llm_requests` table) keyed by persona_id/conversation_id.
5. Everything persona: generation pipeline, memory, evidence, consistency engine, interview engine, evaluation.

### 6.3 Preferred integration shape

Use freellmpool **as a library** (`Pool` / `AsyncPool` + `on_event`) inside our policy layer, not merely as an opaque proxy. Reasons: we need task types, pool semaphores, pre-flight context estimation, and DB provenance around every call — all of which want in-process hooks. The proxy mode remains available for ad-hoc tools and the demo dashboard.

---

## 7. Dataset candidates (recommendation — verify licenses at download time, Phase 7)

No dataset is invented; all are established open datasets. Final license verification is a mandatory step of the download script.

| Dataset | Source | Purpose (brief §12 letter) | License posture (to verify) |
|---|---|---|---|
| PersonaHub | HF `proj-persona/PersonaHub` | A, B — persona seeds/diversity | CC BY-NC-SA 4.0 (research OK; no commercial redistribution) |
| Synthetic-Persona-Chat | HF `google/Synthetic-Persona-Chat` | A, F — persona-grounded dialogues | CC BY 4.0 |
| PersonaChat / ConvAI2 | HF `bavard/personachat_truecased` | B, F — classic persona dialogue baseline | Academic-use custom terms |
| Amazon Reviews 2023 | HF `McAuley-Lab/Amazon-Reviews-2023` (take 1–2 category slices only) | C, H — real product/user evidence for grounding | Research-friendly; do NOT bulk-download all 571M reviews |
| EmpatheticDialogues | HF `facebook/empathetic_dialogues` | F — interview tone realism | CC BY-NC 4.0 |
| MBTI / Big-Five personality sets | Kaggle `datasnaek/mbti-type`; PANDORA (application-gated) | B — personality trait priors | Mixed; PANDORA requires signed access — treat as optional |
| LMSYS-Chat-1M (sample) | HF `lmsys/lmsys-chat-1m` | D, F — conversation quality eval | LMSYS license (research; gated) |
| RouterArena | HF `RouteWorks/RouterArena` | E, G — routing evaluation (eval-only; never train on it) | Apache-2.0 |
| xRouteBench | HF `ulab-ai/xRouteBench` | E, G — router comparison with pre-recorded executions ⇒ zero-cost eval | MIT (repo); dataset card to verify |
| MMLU / GSM8K (small slices) | HF `cais/mmlu`, `openai/gsm8k` | D — model capability sanity probes for health checks | MIT / MIT |

Sizing rule: total raw downloads target < 10 GB; use HF streaming/slicing rather than full dumps.

---

## 8. Recommended integration points (greenfield boundaries)

```
apps/backend  (FastAPI, Python 3.12, package `bebshax`)
    └── bebshax/llm/            ← BebshaX Policy Layer (custom): LLMService abstraction
            router.py           task→pool→candidate selection, per-pool semaphores
            context.py          pre-flight token budgeting (identity+memory+evidence+history+output)
            registry.py         model_registry table sync (freellmpool catalog + awesome-free-llm-apis data.json)
            provenance.py       llm_requests logging (persona_id, conversation_id, attempts, failures)
            health.py           scheduled cheap probes, cooldown state
            adapters/           ← ONLY code allowed to import freellmpool / Ollama APIs
                ↓ uses
        freellmpool (AsyncPool, on_event)   ← MIT, pip-installed
                ↓
        24 free providers … → Ollama (qwen3.5 + one ~3B model)

    └── bebshax/persona/        ← generation, validation, memory, evidence, interview (custom)
    └── PostgreSQL 16 + pgvector (Docker, port 5433) ← personas, evidence, memory, llm_requests, model_registry
apps/frontend  (React + Vite single app — Phase 12)
```

## 9. Open questions — ALL RESOLVED (owner, 2026-08-22)

- **Q1 → Greenfield confirmed.** `e:\BebshaX` is intentionally new; no older codebase exists or should be sought.
- **Q2 → Python 3.12 + FastAPI confirmed.**
- **Q3 → React + Vite single app** covering: business/project setup, persona generation, persona profiles, persona memory, interview/simulation, insights, routing dashboard, provider status, fallback history, request provenance, evaluation metrics.
- **Q4 → No fixed provider list.** Keys arrive via environment/configuration only; the team adds whatever legitimate free-tier accounts it actually has. Keyless providers stay enabled. No limit-evasion mechanisms of any kind.
- **Rename:** project is now **BebshaX** everywhere (packages, env vars `BEBSHAX_*`, DB metadata, UI, docs); SignalLens survives only in rename notes.

## 10. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Free-tier drift (models renamed/killed, limits changed without notice) | High, permanent | Registry refresh job + advisory catalog sync + health-gated routing; contribute `providers.toml` fixes upstream |
| 4 GB VRAM ceiling → local fallback quality is modest | Medium | Treat Ollama as *reliability* fallback only (per brief §24); demo mode caches known-good personas |
| freellmpool is young (83★, single-maintainer risk) | Medium | MIT ⇒ vendorable; our policy layer isolates it behind one interface (`bebshax/llm/adapters/`), swappable for LiteLLM SDK or freelm |
| Persona quality depends on small free models | Medium | Quality-aware routing rations strong-model quota for PERSONA_GENERATION/CRITIC; validation+critic loop catches junk; explicit-fail beats silent degradation |
| Provider ToS on data usage (several free tiers may train on prompts) | Medium | Document per-provider in MODEL_REGISTRY.md; never send real PII (synthetic personas only); demo mode warns |
| Exhibition-day outage of remote providers | High impact, low prob. | DEMO_MODE with cached personas + Ollama tier + keyless providers = three independent safety nets |
| pgvector missing from native PG 16 install | Low | Verify in Phase 1; fall back to `pgvector/pgvector:pg16` Docker image |
