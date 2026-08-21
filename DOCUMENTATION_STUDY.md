# BebshaX — Deep Documentation Study
**Date:** 2026-08-22 | **Status:** Phases 1–3 ✅ Complete | **Current state:** API running, database healthy

---

## Executive Summary

**BebshaX** is a **zero-budget synthetic-user research system** that generates evidence-grounded personas for businesses/products and lets those personas participate in interviews and simulations. The core innovation: aggregate **legitimate free LLM capacity** behind intelligent routing, failover, and context-aware model selection—with a local Ollama model as the final fallback.

**Key principle:** Quality is never silently degraded. If a request can't be served with sufficient context → explicit failure (`ContextWindowExceeded`), not truncation.

---

## 1. What This Project Does

### 1.1 The Research Question
> Can intelligent multi-model routing aggregate free LLM capacity while preserving synthetic persona quality and user experience?

### 1.2 Non-Negotiable Principles
1. **Quality never silently degrades** — no truncating persona context to fit a weaker model, no swapping identity, no hidden fallbacks.
2. **Low answer quality is NOT an infrastructure failure** — it belongs to the evaluation layer (Phase 11), never to fallback logic.
3. **Legitimate free-tier use only** — no fake accounts, no rate-limit evasion, no leaked keys. Teammates add their own legitimate keys.
4. **One AI system** — end users click "Generate Persona"; they never pick model #73. Routing is internal.
5. **OSS-first architecture** — use existing mature libraries behind thin adapters; custom code = personas, memory, evidence, interviews, quality, routing policy, provenance, evaluation, UI.

### 1.3 The Tech Stack (Decided — Not Negotiable)

| Layer | Choice | Why |
|---|---|---|
| **Backend** | Python 3.12 + FastAPI, async | freellmpool is Python; best ML ecosystem |
| **Routing engine** | freellmpool (MIT) as a library | 24 free providers, 222 routes, keyless start, failover/quotas/circuits built in |
| **Database** | PG16 + pgvector on **port 5433** (Docker) | Native PG16 lacks pgvector; this Docker image has it |
| **Local fallback** | Ollama with `qwen3.5:latest` (6.6 GB) | 4 GB VRAM ceiling — no 70B fantasies |
| **Frontend** | React + Vite | Single-page app (Phase 12, not started yet) |
| **Datasets** | Profiles: minimal/dev/eval/full; grounding + eval only | **NO fine-tuning, ever** |

---

## 2. Architecture

### 2.1 Request Path (Current: Phase 3)

```
Caller (persona engine, API, ...)
  ↓
LLMService.complete(LLMRequest{task, messages, constraints})
  • Pre-flight: capability filter + context-window estimate
  • Ineligible routes NEVER called
  • Per-failure-kind fallback (policy-driven)
  • Full ProvenanceRecord on success AND failure
  ↓
ProviderAdapter [BOUNDARY — only code allowed to import provider SDKs]
  ├─ FreellmpoolAdapter → freellmpool AsyncPool.achat()
  │    • Virtual route "freellmpool/auto" 
  │    • freellmpool does provider-level failover internally
  │    • Concrete provider/model recorded in provenance
  └─ OllamaAdapter (Phase 4) → local reliability fallback
```

**Phase 5 adds task→pool routing** across both adapters.

### 2.2 The Four Key Frozen Contracts (All Three Team Members Depend On These)

1. **`LLMService` interface** — entry point for all LLM calls
   - Takes explicit `TaskType` (no LLM classification)
   - Returns `LLMResult` + full `ProvenanceRecord`
   
2. **`ProvenanceRecord`** — all 14 fields required:
   - Provider, model, routing path, attempt #, latency, token counts
   - Failure/fallback reasons, final serving model
   - Used by Phase 6 database, Phase 11 evaluation
   
3. **`TaskType`** — 16 fixed task types (declared by caller):
   - `PERSONA_GENERATION`, `PERSONA_INTERVIEW`, `PERSONA_RESPONSE`
   - `MEMORY_*`, `EVIDENCE_*`, `STRUCTURED_OUTPUT`, `CONTRADICTION_CHECK`, etc.
   - No new types without enum + tests in one commit
   
4. **`ProviderAdapter` base class** — the only place provider SDKs live
   - `candidates()` → list of `RouteCandidate`s per adapter
   - `complete()` → `AdapterCompletion` with real provider/model
   - `OllamaAdapter` and `FreellmpoolAdapter` implement this

**Rule:** Change any of these → all three team members must agree first (RULES.md).

### 2.3 Failure Taxonomy (Closed Set)

**13 `FailureKind`s**, each with explicit `FailurePolicy`:

| Failure | Policy | Why |
|---|---|---|
| `RATE_LIMITED` (429) | Retry once, advance + cooldown | Infrastructure issue |
| `TIMEOUT` | Advance to next | Transient network |
| `CONNECTION` | Retry once, then advance | Network hiccup |
| `SERVER_ERROR` (5xx) | Advance + cooldown | Provider problem |
| `MODEL_UNAVAILABLE` | Advance + cooldown | Model gone |
| `AUTH_INVALID` | Advance + cooldown | Key dead |
| `CONTEXT_WINDOW_EXCEEDED` | Advance to larger model | **Never truncate** |
| `MALFORMED_RESPONSE` | Retry once, then advance | Transient parsing |
| `INTERNAL_ERROR` | **Surface immediately** | Our bug — don't hide it |
| — | — | — |
| `LOW_QUALITY` | **NOT IN THIS LIST** | Quality → Phase 11 evaluation, never fallback |

---

## 3. Team Structure & Parallel Work (Zero Collision)

**Three independent tracks**, each owning disjoint paths:

### 3.1 Current Block (Phases 4–7, any order, no waiting)

| Teammate | Track | Phases | Owns | Status |
|---|---|---|---|---|
| **Tayeb** | A — LLM infra | 4→5 | `bebshax/llm/**`, `scripts/benchmark_ollama.py`, `docs/ROUTING.md` | Ready for Phase 4 |
| **Sazid** | B — Data layer | 6→7 | `bebshax/db/**`, `alembic/`, `data/**`, `scripts/setup_datasets.py` | Ready for Phase 6 |
| **Shehab** | C — Frontend | 12-foundation | `apps/frontend/**`, `docs/API_CONTRACT.md` | Ready for Phase 12 |

**Why they don't collide:**
- A works against frozen `LLMService` + Ollama's API (no DB)
- B consumes frozen `ProvenanceRecord` for database + pulls external datasets
- C builds React views on mock data; only needs `/api/health` from backend

### 3.2 After The Block (Phases 8–15)

| Phase | Owner | Needs | Starts |
|---|---|---|---|
| 8 — Persona engine | Tayeb | 5, 6 (7 for evidence) | Once 5+6 land |
| 9 — Memory | Sazid | 6, 8 (persona IDs) | Once 6+8 land |
| 10 — Interview | Tayeb | 8 (uses 9 when ready) | Once 8 lands |
| 11 — Quality/eval | Shehab | 8, 10 (starts routing half after 5) | After 5 |
| 12 — Frontend live | Shehab | 8/10/11 endpoints | Endpoints land |
| 13 — Integration | All three | 10, 12 | All converge |
| 14 — Testing | All | 13 | Harden after 13 |
| 15 — Docs | All | 14 | Assemble final report |

---

## 4. The Phase Execution Protocol

**When you want to build Phase N:**

1. **Say to your AI tool:** `"Implement phase N"`
2. Agent reads [AGENTS.md](AGENTS.md) + [docs/PHASES.md](docs/PHASES.md)
3. **Gate:** Verify prerequisites ✅ and tests green. Stop if not.
4. **Implement** only within your phase's allowed paths + frozen contracts
5. **Run every exit-criteria command** from the phase spec — all must pass
6. **Mandatory doc updates (same commit as code):**
   - Append `### Phase N — <name> (date)` to [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) with what was built, findings, deviations, new dependencies + R8 review
   - Flip status in [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) roadmap AND [docs/PHASES.md](docs/PHASES.md)
   - Update docs the phase spec lists (e.g., `docs/ROUTING.md` for Phase 4)
7. **Commit** as `Phase N: <summary>` and push to `main`
8. **Report:** What was delivered, test count, deviations, next phase

---

## 5. Current State: Phases 1–3 (✅ Done)

### Phase 1 — Foundation (2026-08-22)
- Repo initialized; scaffold: `apps/backend`, `data/`, `docker-compose.yml`, `.env.example`
- Config: pydantic-settings with `BEBSHAX_*` prefix
- Health endpoint: `GET /api/health` → 200 OK
- **Finding:** Native PG16 lacks pgvector → app DB runs on Docker port **5433**
- Tests: 3/3 green

### Phase 2 — LLM Abstraction (2026-08-22)
- `bebshax.llm` package: `LLMService`, `TaskType`, failure taxonomy, `ProvenanceRecord`
- `ProviderAdapter` boundary + `FakeAdapter` for tests
- `SingleAdapterLLMService` reference impl (will be replaced by `PoolRouter` in Phase 5)
- Tests: 17/17 green

### Phase 3 — freellmpool Integration (2026-08-22)
- Dependency: `freellmpool==0.11.4` (MIT, active, single-maintainer risk mitigated by adapter boundary)
- `FreellmpoolAdapter`: error mapping, concrete-route provenance, keyless smoke test passed
- **Gate B decided:** LiteLLM skipped — all needed providers covered by freellmpool + Ollama
- Boundary enforcement: test proves no provider SDKs outside `adapters/`
- Live keyless smoke: served by `llm7/codestral-latest`, 3 failover attempts in provenance
- Tests: 26/26 green

---

## 6. What's Next: Phase 4 (Tayeb's Track)

**Goal:** Local Ollama becomes a working reliability-fallback backend.

**Key deliverables:**
1. Benchmark script: detect Ollama daemon, measure qwen3.5 perf (time-to-first-token, tokens/sec, latency), recommend a ≤4B fast model
2. `OllamaAdapter`: use httpx directly (no new SDK), map errors, return `AdapterCompletion` with real token counts
3. Unit tests with stubbed httpx (no network); `scripts/smoke_ollama.py` for real calls
4. Update `docs/ROUTING.md` with chosen models + benchmark numbers

**Hardware fact:** 4 GB VRAM ceiling. `qwen3.5:latest` (6.6 GB) runs with CPU offload; a 3–4B Q4 model fits fully.

---

## 7. Key Documents & Their Purpose

| Document | Purpose | Updated |
|---|---|---|
| [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) | Single source of truth: what we're building, decided stack, phase roadmap, architecture diagram | By phase owner after each phase |
| [RULES.md](RULES.md) | **Binding engineering rules R1–R12** that every AI agent/contributor must obey | Only on new rule discovery |
| [AGENTS.md](AGENTS.md) | Contract auto-loaded by Copilot/Cursor/Claude Code — the Phase Execution Protocol, Definition of Done, hard rules digest | Auto-updated with this doc |
| [docs/PHASES.md](docs/PHASES.md) | Executable spec for phases 4–15: goal, prerequisites, allowed paths, steps, exit criteria with commands, docs to update | After each phase |
| [docs/TEAM_ASSIGNMENTS.md](docs/TEAM_ASSIGNMENTS.md) | Who owns which paths, merge rules, contract-change sign-off requirements | After new team members |
| [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | **Append-only log** of what was built, findings, new dependencies + R8 reviews | After every phase + maintenance |
| [docs/AI_INFRASTRUCTURE_AUDIT.md](docs/AI_INFRASTRUCTURE_AUDIT.md) | OSS evaluation (13 routing repos audited), hardware facts (4 GB VRAM ceiling), host environment audit | Once at start |
| [docs/ROUTING.md](docs/ROUTING.md) | How requests flow through the system, freellmpool dependency review, error mapping, provider config, verification commands | After Phases 3, 4, 5 |
| [docs/TEAM_SETUP.md](docs/TEAM_SETUP.md) | Clone→venv→pip→tests in 5 min. Configuration, database setup, everyday commands, pre-push checklist | Link from README |
| [README.md](README.md) | Public entry point: what BebshaX is, quickstart, "how we work" summary, repository layout, AI agent instruction | Link to team docs |

---

## 8. Important Engineering Rules (R1–R12)

### R1 — Adapter Boundary
**Only code inside `apps/backend/bebshax/llm/adapters/` may import `freellmpool`, Ollama clients, or any provider SDK.** Everything else calls `LLMService`. Test-enforced.

### R2 — Quality is Sacred
- Never truncate/drop/compress persona identity/memory/evidence to fit a smaller model.
- If nothing fits → raise `ContextWindowExceeded`. Explicit failure beats silent degradation.
- **Low answer quality is NOT a `FailureKind`** — never trigger fallback for it.

### R3 — Every LLM Call is Governed
- Goes through `LLMService.complete(LLMRequest)` with explicit `TaskType`.
- Produces complete `ProvenanceRecord`: provider, model, routing path, attempts, latency, tokens, failure/fallback reasons.

### R4 — Secrets & Keys
- Keys live in `.env` (gitignored) only. Never in code, config, commits, logs, screenshots.
- Mask keys in output (`gsk_****`). If a key leaks: rotate immediately, tell team.

### R5 — Legitimate Free-Tier Use
- No duplicate accounts, no rate-limit evasion, no scraped APIs, no shared personal keys.
- Each teammate configures their own legitimately-obtained keys via `.env`.

### R6 — Failure Taxonomy is Closed
- New failure kinds need enum + `FailurePolicy` + tests in one PR.
- `INTERNAL_ERROR` (our bugs) must surface immediately, never burn fallback candidates.

### R7 — Tests Gate Everything
- `python -m pytest apps/backend/tests -q` must be green before every commit.
- New behavior ⇒ new tests in the same commit.
- Chaos paths use `FakeAdapter` — never against real providers.

### R8 — Dependencies Need Written Review
- Before adding any dependency, record: why needed, what replaces, license, maintenance, necessity.
- Goes in the implementation log before installing.

### R9 — Datasets
- Only through `scripts/setup_datasets.py` with profiles (minimal/dev/eval/full).
- Every dataset in `data/DATASETS.md`: source, license, size, purpose, download+preprocessing, required/optional.
- **NO model training/fine-tuning.**

### R10 — Working Style
- Incremental phases; don't start phase N while N-1 is red.
- After each phase: tests → fix → update `docs/IMPLEMENTATION_PLAN.md` → commit.
- Commit format: `Phase N: <what>` or `fix:/docs:/chore: <what>`.
- `main` stays green and demoable.

### R11 — User Experience
- End users see ONE AI system ("Generate Persona"), never provider/model pickers.
- Routing internals exposed only in the developer dashboard, clearly labeled.
- Demo mode must clearly indicate when cached results are shown.

### R12 — AI Agents Follow The Contract
- Every agent/tool obeys [AGENTS.md](AGENTS.md).
- A task with stale docs is an **unfinished task** — update docs in the same commit as code.
- CI enforces the test gate on every push.

---

## 9. The Host Machine's Hardware Constraints

| Resource | Value | Implication |
|---|---|---|
| **CPU** | Intel i5-12500H (12c/16t) | Fine for API serving + preprocessing |
| **RAM** | 15.7 GB total | Must leave ≥6 GB for OS+services → ~9 GB app ceiling |
| **GPU** | RTX 3050 Laptop, **4 GB VRAM** | Only ~3–4B Q4 models fit fully in VRAM; 7–8B Q4 runs with CPU offload |
| **Disk** | 195 GB free | Plenty for datasets + a few models |

**Local Model Policy:**
- Fast local fallback: a ~3–4B instruct model (fully GPU-resident, low latency)
- Quality local fallback: `qwen3.5:latest` (6.6 GB, partial CPU offload — works, slower)
- **A 70B model is impossible. Do not configure one.**

---

## 10. The Free Provider Ecosystem (via freellmpool)

**freellmpool catalogs:**
- **~24 free providers** with **222 live routes**
- **407 models** available keyless or with team's own keys
- **Keyless providers:** Pollinations, OVHcloud, Kilo, LLM7
- **With keys:** Groq, Google AI Studio, NVIDIA NIM, Mistral, Cerebras, OpenRouter, Cohere, GitHub Models, Cloudflare, HF router, etc.

**Legitimate signup (no credit card required):**
- Groq: `console.groq.com/keys`
- Google AI Studio: `aistudio.google.com/apikey`
- NVIDIA NIM: `build.nvidia.com`
- Mistral: `console.mistral.ai/api-keys`
- Cerebras: signup page
- OpenRouter: `openrouter.ai/keys`
- Cohere: `dashboard.cohere.com/api-keys`
- GitHub Models: any PAT

---

## 11. How to Start Working on This Project

### For a Team Member (Read Once)

1. **Clone + setup (5 min):**
   ```powershell
   git clone https://github.com/Tayebbb/BebshaX.git
   cd BebshaX
   python -m venv .venv
   .venv\Scripts\pip install -e "apps/backend[dev]"
   .venv\Scripts\python -m pytest apps/backend/tests -q  # verify green
   ```

2. **Read (20 min, in this order):**
   - [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) — what we're building, architecture, phase roadmap
   - [RULES.md](RULES.md) — binding rules R1–R12
   - [docs/TEAM_ASSIGNMENTS.md](docs/TEAM_ASSIGNMENTS.md) — find your name, understand your track
   - Your phase's section in [docs/PHASES.md](docs/PHASES.md)

3. **Build your phase:**
   ```
   Tell your AI tool: "Implement phase N"
   Verify: tests green + doc updates included + no secrets in diff
   Rebase + push
   ```

### For an AI Tool Working in This Repo

1. **Auto-load [AGENTS.md](AGENTS.md)** (this file does it)
2. **When asked to build:** resolve the phase → load spec from [docs/PHASES.md](docs/PHASES.md)
3. **Gate:** verify prerequisites ✅ and tests green
4. **Stay in scope:** only touch allowed paths + frozen contracts
5. **Implement incrementally** with tests in the same commit
6. **Mandatory doc updates (same commit):**
   - Append `### Phase N — <name> (date)` to implementation log
   - Flip status in roadmaps
   - Update docs the spec lists
7. **Commit** as `Phase N: <summary>` and push `origin main`

---

## 12. Project Status Dashboard

| Item | Status | Notes |
|---|---|---|
| **Backend running** | ✅ | FastAPI on port 8000, `/api/health` returns 200 |
| **Database running** | ✅ | pgvector on Docker port 5433, healthy |
| **Tests** | ✅ 26/26 green | No known issues |
| **Phases 1–3** | ✅ Complete | Foundation, LLM abstraction, freellmpool integration |
| **Phase 4 ready** | ✅ | Ollama benchmark + adapter spec written in Phase spec |
| **Parallel block (4/6/12)** | ⬜ Ready to start | Tayeb (4→5), Sazid (6→7), Shehab (12-foundation) |
| **Dependencies locked** | ✅ | requirements.lock synced |
| **CI passing** | ✅ | `.github/workflows/ci.yml` runs pytest on every push |
| **Secrets in repo** | ✅ None | `.env` gitignored, keys in `.env.example` only |

---

## 13. Key Insights from the Docs

### The Core Innovation: Adapter Boundary
The **adapter boundary** at `bebshax/llm/adapters/` is the architectural keystone:
- **Isolates** provider SDK complexity (freellmpool, Ollama, future providers)
- **Enforces** via tests that nothing outside imports them
- **Allows** swapping routing engines without touching application code
- **Example:** if freellmpool ever dies, a new `NovaRouter` adapter is a drop-in replacement

### Quality ≠ Infrastructure Failure
**Critical mindset shift:** Low answer quality is NOT an infrastructure problem. Falling back won't help. Quality belongs to the evaluation layer (Phase 11), which will measure and improve it offline.

### Explicit > Silent
Rather than truncate context or hide failures, **raise `ContextWindowExceeded`** and let the caller decide. Transparency + explicitness = trustworthiness.

### Greenfield Freedom
No legacy code to preserve. This is a fresh build, which means every architectural decision can be optimized for the routing requirement instead of retrofitting one onto existing code.

### Keyless Start
Even with zero API keys, the system works (Pollinations, OVHcloud, Kilo, LLM7). This lowers the barrier to entry and demonstrates the routing is doing real work.

### The 4 GB VRAM Ceiling
The local fallback strategy is shaped entirely by this hardware constraint. A 70B model is not an option. The team thoughtfully chose `qwen3.5` as a quality local model that runs with partial CPU offload, and Phase 4 will benchmark and pick a faster ≤4B model to pair with it.

---

## 14. Common Questions Answered

**Q: Can I start Phase 4 before Phase 5?**
Yes — they're independent. Phase 4 (Ollama adapter) doesn't depend on Phase 5 (routing). They can land in any order.

**Q: What if I need to change `ProvenanceRecord`?**
All three team members must agree first. It's a shared contract that Phases 6 (database), 8 (persona engine), and 11 (evaluation) all depend on.

**Q: Can I add `requests` or `aiohttp` alongside `httpx`?**
Not for LLM calls — they must go through the adapter boundary, which uses `httpx` everywhere. Different HTTP clients are OK outside the LLM path.

**Q: What if freellmpool has a bug?**
The adapter boundary is your safety net. You can patch it there, or swap to a different routing engine without touching application code.

**Q: When should I commit?**
After every completed step from the phase spec. Small commits. Before pushing, run tests and check for secrets.

**Q: What does "stale docs" mean?**
Code changes without updating the implementation log, status tables, or phase specs. Treat docs like tests — they're part of the contract.

---

## 15. Next Steps

1. **Verify the system is running:**
   ```powershell
   # Backend: GET http://localhost:8000/api/health
   # Database: docker ps | grep bebshax-db (should be "healthy")
   ```

2. **Run the test suite:**
   ```powershell
   .venv\Scripts\python -m pytest apps/backend/tests -q
   ```

3. **Pick your phase:** If you're Tayeb, say `"Implement phase 4"`. If Sazid, `"Implement phase 6"`. If Shehab, `"Implement phase 12-foundation"`.

4. **The AI agent will handle the rest:** gate-check, implement in-scope, run verification, update docs, commit, push.

---

**End of Deep Study**

This document captures the full context, architecture, rules, and coordination strategy of the BebshaX project. All subsequent work flows from these principles.
