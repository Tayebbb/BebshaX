# BebshaX — AI / LLM Implementation Plan (plain-English)

> **The one-sentence answer:** BebshaX aggregates and routes legitimate free LLM capacity without merging answers, while persona generation separately uses a trained CPU TF-IDF/NMF source selector with no LLM call or fallback.

Companion docs: [ROUTING.md](ROUTING.md) is the reference (tables, failure codes, dependency reviews). This file explains the _mental model_ — read this first.

---

## 1. Three words people confuse

| Word                                      | Meaning                                                                 | Do we do it?                                                                        |
| ----------------------------------------- | ----------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| **Aggregation**                           | Many providers/keys pooled into one usable capacity pool                | ✅ **Yes** — this is the whole point of the project (zero budget → pool free tiers) |
| **Routing**                               | Pick _which_ model handles _this_ request, and what to do when it fails | ✅ **Yes** — `PoolRouter`, task→pool map, fallback ladder                           |
| **Ensembling** (voting / merging answers) | Ask N models the same thing, then combine/vote on the answers           | ❌ **No** — see [§7](#7-why-no-voting-or-answer-merging)                            |

So: **aggregate the supply, route each request, never blend the outputs.**

---

## 2. The layer cake

```mermaid
flowchart TD
    A["LLM feature code<br/>copilot · interview · memory · research"] -->|"LLMRequest(task=...)"| B
    P["Four persona generation paths"] --> ML["MLPersonaAdapter<br/>CPU TF-IDF/NMF + source selection"]
    ML --> STORE["Existing persona schemas / storage<br/>SYNTHETIC source-model provenance"]
    B["LLMService.complete()<br/>THE only entry point"] --> C
    C["PoolRouter — BebshaX policy<br/>task → pool → candidates → filter → attempt → fallback"] --> D
    C --> E
    D["FreellmpoolAdapter<br/>(remote, free tiers)"] --> F["freellmpool library<br/>18 providers (0.11.4 catalog)<br/>keyless start supported"]
    E["OllamaAdapter<br/>(local, last resort)"] --> G["Ollama on this machine<br/>llama3.2:3b / qwen3:4b"]
    C --> H[("ProvenanceRecord →<br/>llm_requests table")]
```

Two things do the heavy lifting, and they are **different jobs**:

- **freellmpool** (a third-party MIT library) = the **aggregator**. It knows about 18 free providers (the catalog bundled with the pinned 0.11.4 — verified 2026-08-28, re-verified 2026-09-06; earlier docs said ~24 providers / 222 routes, the figure from the 2026-08-22 audit of the upstream project, which the installed catalog does not match), rotates keys, tracks quotas, honours `Retry-After`, trips circuit breakers. We did **not** write this — rule R10 forbids rebuilding routers/gateways.
- **`PoolRouter`** ([apps/backend/bebshax/llm/router.py](../apps/backend/bebshax/llm/router.py)) = **our policy**. It knows about _tasks_, _context budgets_, _capabilities_, _cooldowns_ and _provenance_ — things a generic aggregator can't know.

To BebshaX, the entire remote world is a single virtual route called `freellmpool/auto`. The real provider/model that ended up serving (e.g. `llm7/codestral-latest`) is reported back and stored, so provenance never says "auto".

> **Temporary (2026-08-26):** a third adapter, `OpenRouterAdapter`, currently sits as _first preference_ in the remote pools — **testing only**, per owner decision. Keyless it contributes no routes and everything behaves as documented here. Its position contradicts §10's capacity math (50 req/day at $0) and must be revisited before production.

---

## 3. The single entry point rule

Every LLM call in the codebase — no exceptions — looks like this:

```python
result = await llm.complete(
    LLMRequest(
        task=TaskType.PERSONA_INTERVIEW,   # the caller ALWAYS knows its task
        messages=[...],
        json_mode=True,                    # capability requirement
        max_output_tokens=400,
        persona_id=persona.id,
    )
)
result.text          # the answer
result.provider      # who actually served it
result.provenance    # the full audit trail
```

- No feature file may `import openai` / `import freellmpool` — provider SDKs live **only** in [apps/backend/bebshax/llm/adapters/](../apps/backend/bebshax/llm/adapters/), and a test enforces it (R1/D2).
- **No LLM is used to classify the task.** The 18 `TaskType` values are declared by the caller in code (D7). Cheap, deterministic, debuggable.

---

## 4. What happens on one request — 7 steps

Source: [apps/backend/bebshax/llm/router.py](../apps/backend/bebshax/llm/router.py) + [apps/backend/bebshax/llm/service.py](../apps/backend/bebshax/llm/service.py).

| #   | Step                   | Where                                                                          | In plain English                                                                                                                                                                                                                                                       |
| --- | ---------------------- | ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **Task → pool**        | [pools.py](../apps/backend/bebshax/llm/pools.py)                               | A lookup table, not `if/else`. `PERSONA_INTERVIEW` → `conversation` pool.                                                                                                                                                                                              |
| 2   | **Throttle**           | `asyncio.Semaphore` per pool                                                   | Each pool has a concurrency cap (e.g. `reasoning` = 2) so we don't hammer free tiers.                                                                                                                                                                                  |
| 3   | **Collect candidates** | adapter `.candidates()`                                                        | Ask each adapter in the pool what routes it can serve _right now_. Ollama discovers models live from `/api/tags`.                                                                                                                                                      |
| 4   | **Rank**               | `ranker` hook                                                                  | Production = the §10 quota-aware ranker. An explicit per-request preference (`LLMRequest.preferred_provider/preferred_model`, None = **Auto**) is then prioritized — advisory, never exclusive, so an unavailable preferred model degrades to Auto instead of failing. |
| 5   | **Pre-flight filter**  | `filter_eligible()` + [estimator.py](../apps/backend/bebshax/llm/estimator.py) | Drop routes that are cooling down, can't do JSON/tools, or whose context window is smaller than our token estimate. **Ineligible routes are never called.**                                                                                                            |
| 6   | **Attempt loop**       | `attempt_candidates()`                                                         | Try candidate #1. If it fails, look up the failure kind in `FAILURE_POLICIES` → retry once / move on / cool it down / surface immediately. Then candidate #2, #3…                                                                                                      |
| 7   | **Record**             | [provenance.py](../apps/backend/bebshax/llm/provenance.py)                     | Write every candidate considered, every attempt, latencies, tokens, and the final serving model — **on success _and_ on failure**.                                                                                                                                     |

### The critical guarantee (R2)

If **nothing** can fit the prompt, we raise `ContextWindowExceeded`. We **never** trim the persona, memories, or evidence to squeeze into a smaller model. The token estimator deliberately _over_-estimates (chars ÷ 3.5) so a mis-estimate can only push us to a **roomier** model — never toward truncation.

---

## 5. The routing table

Configuration as **data**, so extending it = edit a table + add a test, never add a code branch.

| Pool           | Order                                                                                                                                                                                 | Max concurrent | Tasks routed here                                                                                                                 |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `reasoning`    | openrouter† → freellmpool → ollama                                                                                                                                                    | 2              | PERSONA_GENERATION, PERSONA_REFINEMENT, PERSONA_VALIDATION, CONTRADICTION_CHECK, CRITIC, PERSONA_NARRATIVE, BEHAVIORAL_SIMULATION |
| `conversation` | **ollama → freellmpool → openrouter** (judged gate 2026-08-26/27, 3 runs: local 3B 9.65 / 9.05 / 9.2 vs cloud-fast 8.25 / 8.05 / 8.2; n = 1 persona × 5 questions; ~5–7 s/turn local) | 5              | PERSONA_INTERVIEW, PERSONA_RESPONSE                                                                                               |
| `structured`   | openrouter† → freellmpool → ollama                                                                                                                                                    | 3              | STRUCTURED_OUTPUT, EVIDENCE_EXTRACTION, EVIDENCE_CLASSIFICATION, BROWSER_AGENT, TOOL_CALLING                                      |
| `fast`         | **ollama → freellmpool → openrouter** | 5 | MEMORY_RETRIEVAL, MEMORY_SUMMARIZATION |
| `long_context` | openrouter† → freellmpool → ollama                                                                                                                                                    | 2              | REPORT_GENERATION                                                                                                                 |
| `local`        | ollama only                                                                                                                                                                           | 2              | reserved for explicit local-only work                                                                                             |
| `emergency`    | **ollama → freellmpool**                                                                                                                                                              | 2              | EMERGENCY_FALLBACK (local **first** — when the internet is the problem)                                                           |

† testing-only first preference — see the note in [§2](#2-the-layer-cake); keyless → contributes no routes.

`PERSONA_GENERATION`, `PERSONA_REFINEMENT`, and `PERSONA_VALIDATION` remain as
compatibility enum/map entries. Production business/study/role/dataset persona
writing bypasses the pools and uses ML selection.

Two invariants worth memorising:

1. **Every pool includes the local adapter.** Conversation/fast and emergency are local-first; other remote pools place Ollama last. A local route still requires a running daemon, a loadable model, and enough context; total failure remains possible.
2. **All 18 task types must be mapped.** A unit test fails the build if someone adds a `TaskType` without a pool — and a second test fails on references to task types that don't exist.

---

## 6. Fallback: what counts as a failure

Only **infrastructure** problems trigger fallback. Full mapping table in [ROUTING.md](ROUTING.md#failure-classification); the shape of it:

| Failure kind                                                                                                         | Retry same route? | Try next? | Cool the route down?        |
| -------------------------------------------------------------------------------------------------------------------- | ----------------- | --------- | --------------------------- |
| `RATE_LIMITED` (429), `QUOTA_EXHAUSTED`, `SERVER_ERROR`, `AUTH_INVALID`, `MODEL_UNAVAILABLE`, `PROVIDER_UNAVAILABLE` | no                | yes       | **yes** (60 s)              |
| `CONNECTION`, `MALFORMED_RESPONSE` (empty reply)                                                                     | **once**          | yes       | no                          |
| `TIMEOUT`, `CONTEXT_WINDOW_EXCEEDED`, `CAPABILITY_UNSUPPORTED`, `CONTENT_REFUSAL`                                    | no                | yes       | no                          |
| `INTERNAL_ERROR` (our own bug)                                                                                       | no                | **no**    | no — surface it immediately |

### The thing that is deliberately **missing** from that list

There is **no `LOW_QUALITY` failure kind**, and a test enforces that there never will be. A weak-but-valid answer is a **content** problem, handled by:

- content/schema validation in the calling feature (the retained LLM persona compatibility pipeline has one refinement round), and
- the evaluation layer, [apps/backend/bebshax/evaluation/](../apps/backend/bebshax/evaluation/).

If bad answers could trigger silent re-routing, our research question ("can free capacity preserve quality?") would be unanswerable — the infrastructure would be hiding the very thing we're measuring.

---

## 7. Why no voting or answer merging

The obvious idea is "ask 3 free models and pick the best". We do **not**, for four reasons:

1. **It multiplies free-tier consumption by 3–5×** for the same user action — the opposite of what a zero-budget project needs (R5).
2. **Latency.** Interviews are interactive; the slowest model would set the pace of every turn.
3. **Merging personas is incoherent.** Averaging three personas produces a fourth person nobody described. Persona identity must stay one consistent voice.
4. **Judging needs another LLM call** — and a free judge model grading free worker models is a weak signal we'd then be tempted to trust.

**What we do instead:** LLM features use governed calls and explicit validation. The separate persona model blends lexical/topic similarity scores to select whole source profiles; that is not voting on LLM answers or merging persona identities.

**Where multi-sampling is legitimate:** offline evaluation runs in [apps/backend/bebshax/evaluation/](../apps/backend/bebshax/evaluation/) and the routing simulator — those _do_ aggregate many runs, but into **metrics and reports**, never into a user-facing answer.

---

## 8. How each feature actually uses the LLM

### Persona generation — zero LLM calls

[MLPersonaAdapter](../apps/backend/bebshax/personas/ml_adapter.py) is shared by
legacy business, study sync/jobs/regeneration, workflow-role, and dataset paths.

```mermaid
flowchart LR
    A["Business / study / role / dataset context"] --> B["Strict context + hard age bounds"]
    B --> C["Local fitted TF-IDF/NMF<br/>diversity-aware source selection"]
    C --> D["Complete synthetic source bundles"]
    D --> E["Existing schemas / DB JSON<br/>source-model provenance"]
    E --> F["Unchanged LLM interviews and memory"]
```

Key points:

- Training fits vocabulary/IDF, topics, and representations on approved synthetic records. It does not fine-tune an LLM or invent new identities.
- Source occupation/location/full narratives are retained. Role/location hints do not guarantee customer fit; explicit ages in 18–95 are hard bounds. Income/budget/OCEAN values are not inferred.
- All claims are `SYNTHETIC`, with no observed citations. Missing/invalid artifacts return 503; unsupported/exhausted contexts return 422. No LLM/template/skeleton fallback writes profiles.
- Active owner-scoped source exclusions prevent sequential reuse, not concurrent cross-process duplicates. Existing multi-role `failed_roles` behavior remains.
- The explicit legacy LLM path remains for compatibility only; see [PERSONA_ENGINE.md](PERSONA_ENGINE.md). Current model and baseline results are in [MODEL_CARD.md](../ml_persona/MODEL_CARD.md): the NMF blend underperforms lexical TF-IDF.

### Interview — exactly 1 call per turn

[apps/backend/bebshax/interview/engine.py](../apps/backend/bebshax/interview/engine.py)

The prompt is assembled from: identity card + business context + objective + **retrieved memories** + evidence themes + **the full prior turn history** (never silently dropped). One `PERSONA_INTERVIEW` call → the persona's reply → both turns persisted. Replies pass through deterministic **format** normalization (think-blocks, whole-reply fences, speaker labels — [normalization.py](../apps/backend/bebshax/interview/normalization.py)); answer _content_ is never rewritten (R2).

### Memory — retrieval is math, not an LLM

[apps/backend/bebshax/memory/scoring.py](../apps/backend/bebshax/memory/scoring.py)

$$\text{score} = 0.60 \cdot \cos(\text{query}, \text{memory}) + 0.25 \cdot e^{-\ln 2 \cdot \frac{\text{age}_h}{48}} + 0.15 \cdot \text{importance}$$

Relevance dominates, recency keeps conversations fresh (48 h half-life), importance lets reflections outrank chit-chat. **An LLM is used only for `reflect()`** — distilling ≥8 recent episodic memories into ≤3 durable first-person insights via `MEMORY_SUMMARIZATION`. That call is best-effort: unparseable output logs a warning and returns nothing rather than breaking a conversation.

### Evaluation — no LLM judge in the request path

[apps/backend/bebshax/evaluation/](../apps/backend/bebshax/evaluation/) scores schema validity, grounding ratio (share of `OBSERVED`/evidence-linked attributes), rule consistency, and contradiction scans — mostly deterministic, run offline, aggregated into reports.

---

## 9. Provenance: one row per LLM request

Every LLM request produces a `ProvenanceRecord` → the `llm_requests` table:

- `request_id`, `task`, `pool`, `persona_id`, `conversation_id`
- `routing_path` — every candidate **considered**, including skipped ones with the reason (`[skipped: context 8192 < ~12000]`, `[skipped: cooling down for 43s more]`)
- `attempts[]` — per attempt: provider, model, latency, success, failure kind + detail, why we moved on, adapter notes (e.g. freellmpool's own internal failover count)
- `served_by_provider` / `served_by_model` — the **concrete** route, never `auto`
- token counts, total latency, success flag

LLM provenance identifies the actual serving route and recorded usage. ML profiles instead store their source/revision/record ID and model version in existing persona fields; they create no fabricated LLM request or provider-cost record.

---

## 10. Capacity: making the free tiers last

The historical 2026-08-25 plan targeted approximately **100 personas plus interviews/day** on $0, with 2–5M tokens/day estimated. This was a planning target, not measured throughput or a near-real-time guarantee. Current ML profile selection consumes no LLM generation quota; copilot/interview/report traffic still does. End-to-end capacity needs a new measured workload rather than extrapolation from warm model timing.

### We already own the "cycler"

What GitHub gateways like _uni-api_ / _one-api_ offer — rotating across free providers/keys with cooldowns — already exists here as freellmpool + `PoolRouter`. Alternatives were researched (2026-08-25) and rejected:

| Alternative                  | Verdict                    | Why                                                                                                                               |
| ---------------------------- | -------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| uni-api (Apache-2.0, active) | ❌ rejected                | An extra proxy deployment duplicating `PoolRouter` + freellmpool; its multi-account rotation features are exactly what R5 forbids |
| one-api (36k★, stale ~1 yr)  | ❌ rejected                | Web-UI gateway in Go; same duplication argument as the Gate B LiteLLM skip                                                        |
| gpt4free-class tools         | ❌ rejected                | Reverse-engineered private endpoints — ToS violation, R5 non-negotiable                                                           |
| OpenRouter free models       | ⚠️ minor extra pool member | Verified: 20 req/min, **50 req/day** at $0; extra accounts do **not** raise limits (capacity is governed globally per their docs) |

### The actual gaps (built 2026-08-26)

Capacity comes from **one legitimate key per provider** (Groq, Gemini, Mistral, Cerebras, GitHub Models, Cloudflare, NVIDIA, Cohere, HF, …) plus routing that drains all daily quotas _evenly_:

| Piece                         | Status | Where                                                                                                                                          |
| ----------------------------- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `scripts/measure_capacity.py` | ✅     | replays a live traffic mix; reports tokens/provider                                                                                            |
| Quota ledger                  | ✅     | [quota.py](../apps/backend/bebshax/llm/quota.py) — `PROVIDER_QUOTAS` data table + in-memory day counters seeded from `llm_requests` at startup |
| Quota-aware ranker            | ✅     | `quota_aware_ranker(ledger)` wired into `PoolRouter` in `create_app`; capped providers sink, stable sort keeps pool order otherwise            |
| Persistent cooldowns          | ✅     | `model_registry.cooldown_until` via [capacity_state.py](../apps/backend/bebshax/db/capacity_state.py); restored at startup, survive restarts   |
| `GET /api/routing/capacity`   | ✅     | used today / caps / remaining fraction per concrete provider                                                                                   |

Quota numbers in `PROVIDER_QUOTAS` marked "verify at signup" are conservative placeholders — correct them as keys are added.

Honest ceiling: real-time + free tiers is bounded by the _sum of per-minute limits_ (~tens of req/min). If bursts ever exceed it, the options are a visible queue or batching bulk simulations — never account multiplication or limit evasion (R5).

---

## 11. Status and what's next

| Capability                                                                               | State                                                                                                       |
| ---------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `LLMService` + task types + failure taxonomy + provenance                                | ✅ Phase 2                                                                                                  |
| freellmpool aggregation adapter (keyless verified)                                       | ✅ Phase 3                                                                                                  |
| Ollama local fallback (benchmarked on 4 GB VRAM)                                         | ✅ Phase 4                                                                                                  |
| `PoolRouter`: pools, context budget, cooldowns, concurrency                              | ✅ Phase 5                                                                                                  |
| Provenance + model registry persisted to Postgres                                        | ✅ Phase 6                                                                                                  |
| Original persona / memory / interview delivery | ✅ Phases 8–10; current persona writing uses ML, interviews/memory retain LLM routing |
| CPU Persona ML source selection | Maintenance 2026-09-09; four runtime paths, trained/evaluated with documented limitations, not phase 16 |
| Routing strategy experiments + evaluation metrics                                        | ✅ Phase 11                                                                                                 |
| **Registry-driven ranking** (quality/latency/health scores feeding the `ranker` hook)    | ⬜ open — hook exists, scores not wired                                                                     |
| **Tool calling**                                                                         | ⬜ open — no adapter advertises `supports_tools`, so `TOOL_CALLING` fails explicitly rather than pretending |
| **Quota-aware capacity layer** (ledger, ranker, persistent cooldowns, capacity endpoint) | ✅ built 2026-08-26, live-verified — see [§10](#10-capacity-making-the-free-tiers-last)                     |
| Original full test matrix / acceptance tests | ✅ Phase 14, 2026-08-28; unchanged historical acceptance, not current ML publication gates |

---

## 12. How to extend it (the 3 common changes)

| You want to…                     | Do this                                                                                                     | Don't do this                                                 |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| **Add a task type**              | Add to `TaskType`, add a row to `TASK_POOL_MAP`, add a test                                                 | Add an `if task == ...` branch in the router                  |
| **Add a provider**               | Configure it in freellmpool (env keys), or write a new `ProviderAdapter` in `adapters/` + name it in a pool | Import a provider SDK in feature code                         |
| **Change how models are picked** | Pass a `ranker` into `PoolRouter(...)`                                                                      | Reorder logic inside `filter_eligible` / `attempt_candidates` |

---

## 13. FAQ

**Does the user ever pick a model?** No. End users click "Generate Persona". Model selection is the backend's job; the developer dashboard exposes routing for _us_, not for them.

**What if I have zero API keys?** Supported and tested — freellmpool starts keyless, and Ollama is local. Teammates add their own legitimately-owned keys via `.env`.

**What does the persona model need?** Both Python packages installed with
the [runtime constraints](../ml_persona/constraints.txt) and a trusted compatible
local artifact. A fresh checkout/image lacks weights; follow [ML setup](SETUP.md#persona-ml-artifact).
No GPU/API key is needed. The model is lazy-loaded/cached; restart after replacement.

**What if all free providers are exhausted?** The ladder ends at Ollama, which serves `llama3.2:3b`. Chaos-tested. If Ollama is also down, you get `AllCandidatesFailed` with the complete attempt trail — an honest error, not a fabricated answer.

**Why do we need Ollama at all — isn't freellmpool enough?** Ollama is **insurance, not horsepower**:

1. Every remote free tier can fail _at the same time_ — a shared 429 storm, an internet outage, zero keys configured, or a provider policy change. Ollama is the only route we fully control: no quota, no rate limit, no ToS, no network.
2. It can serve when remote routes fail, provided the daemon/model/context are available. Pool order differs by task; emergency is local-first. It is not fallback for ML artifact failures.
3. It makes zero-API-keys a supported configuration for teammates and demos.
4. It is deliberately **not** counted as capacity: ~25 tok/s on the 4 GB card (~2M tokens/day theoretical ceiling). The capacity plan in [§10](#10-capacity-making-the-free-tiers-last) never relies on it for volume — resilience is this tier's only job.

**Why not just use LiteLLM / build a gateway?** Gate B decision (recorded in [ROUTING.md](ROUTING.md)): the needed provider surface is already covered, and a proxy would add Postgres/Prisma/Redis-scale infrastructure for capabilities we have. R10 forbids building our own gateway.

**How does Ollama connect to the website if it's hosted (e.g. Vercel)?** It doesn't — the arrow points the other way. The browser talks to the FastAPI backend; the **backend** calls Ollama at `OLLAMA_API_BASE` (default `http://localhost:11434`, read in [ollama_adapter.py](../apps/backend/bebshax/llm/adapters/ollama_adapter.py)). So the question is only ever _where the backend runs relative to Ollama_:

| Topology                                                | How Ollama is reached                                                     | Caveats                                                                                                                                                               |
| ------------------------------------------------------- | ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A. Everything on the dev PC** (recommended for demos) | `localhost` — zero config                                                 | Expose the site publicly with one Cloudflare Tunnel / ngrok to `:8000`; PC must be on                                                                                 |
| **B. Frontend on Vercel, backend on the dev PC**        | Still `localhost` to the backend                                          | Tunnel only the backend; point the frontend's API base at the tunnel URL; tighten `allow_origins` to the Vercel domain first                                          |
| **C. Backend in the cloud, Ollama at home**             | `OLLAMA_API_BASE=https://<tunnel-host>` in the cloud env — no code change | Inverts Ollama's purpose (internet now sits inside the "no-internet" tier); Ollama has **no auth**, so never expose `:11434` raw — Cloudflare Access / Tailscale only |

This repository's Vercel setup hosts the frontend and calls a separately hosted API. The old ~44 s persona-generation and 40–89 s interview figures were LLM-era observations, not current ML timing or generic platform limits. The backend still has process-local state and needs its local ML artifact; deployment guidance is in [SETUP.md](SETUP.md). If the local tier is unreachable it contributes no usable route; requests succeed elsewhere or fail explicitly.

**Is a slow/dumb answer a failure?** No. Infrastructure only reacts to 429s, quotas, timeouts, 5xx, context, and capability errors. Quality is measured, not routed around.
