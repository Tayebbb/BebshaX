# Failover & Routing

The complete failure-handling contract: pools, the task map, the closed failure taxonomy, cooldowns, and context budgeting. Strategy background lives in [ROUTING.md](ROUTING.md); architecture context in [ARCHITECTURE.md](ARCHITECTURE.md).

**Scope after Persona ML maintenance (2026-09-09):** these are LLM routing
policies. All four production persona-generation paths use the separate local
`MLPersonaAdapter`. A missing/invalid bundle returns 503 `ml_persona_unavailable`;
unsupported/exhausted selection returns 422 `ml_persona_unsupported_context`.
These API errors are not new `FailureKind` values and never trigger LLM persona
fallback. Copilot, interviews, and other LLM features retain this routing layer.
See [PERSONA_ENGINE.md](PERSONA_ENGINE.md).

## Pools (config-as-data, `llm/pools.py`)

Order inside a pool = preference order. Bold = local-first.

| Pool         | Adapter order                         | max_concurrency |
| ------------ | ------------------------------------- | --------------- |
| reasoning    | openrouter → freellmpool → ollama     | 2               |
| conversation | **ollama** → freellmpool → openrouter | 5               |
| long_context | openrouter → freellmpool → ollama     | 2               |
| structured   | openrouter → freellmpool → ollama     | 3               |
| fast         | **ollama** → freellmpool → openrouter | 5               |
| local        | ollama                                | 2               |
| emergency    | **ollama** → freellmpool              | 2               |

`conversation` is local-first by measurement, not ideology: the 2026-08-26/27 gate (three runs, n = 1 persona × 5 questions) scored `llama3.2:3b` 9.65 / 9.05 / 9.2 on interview quality at ~5–7 s/turn versus 8.25 / 8.05 / 8.2 for the cloud-fast route at ~53 s / 2.5 s / 56 s — full table and caveats in [ROUTING.md](ROUTING.md).

## Task → pool map (18 task types)

| Pool         | Tasks                                                                                                                             |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| reasoning    | PERSONA_GENERATION, PERSONA_REFINEMENT, PERSONA_VALIDATION, CONTRADICTION_CHECK, CRITIC, PERSONA_NARRATIVE, BEHAVIORAL_SIMULATION |
| conversation | PERSONA_INTERVIEW, PERSONA_RESPONSE                                                                                               |
| structured   | EVIDENCE_EXTRACTION, EVIDENCE_CLASSIFICATION, STRUCTURED_OUTPUT, BROWSER_AGENT, TOOL_CALLING                                      |
| fast         | MEMORY_RETRIEVAL, MEMORY_SUMMARIZATION                                                                                            |
| long_context | REPORT_GENERATION                                                                                                                 |
| emergency    | EMERGENCY_FALLBACK                                                                                                                |

Both tables are data, not branches — extending them means adding a row plus a test (`tests/llm/test_pools.py` enforces every task type is mapped).

Persona-generation/refinement/validation task values remain for compatibility;
their table entries do not imply production LLM persona writing.

## Failure taxonomy (closed set, `llm/failures.py`)

13 kinds. **Low answer quality is deliberately not a failure kind** — it belongs to the quality/eval layer, never to routing (owner rule, 2026-08-22). New kinds require enum + policy + tests in one commit (R6).

| FailureKind             | retry same once |              try next              |         cooldown         | cooldown scope |
| ----------------------- | :-------------: | :--------------------------------: | :----------------------: | :------------: |
| TIMEOUT                 |        —        |                 ✓                  |            —             |       —        |
| CONNECTION              |        ✓        |                 ✓                  |            —             |       —        |
| RATE_LIMITED            |        —        |                 ✓                  |            ✓             |  **provider**  |
| QUOTA_EXHAUSTED         |        —        |                 ✓                  |            ✓             |  **provider**  |
| SERVER_ERROR            |        —        |                 ✓                  |            ✓             |     route      |
| PROVIDER_UNAVAILABLE    |        —        |                 ✓                  |            ✓             |     route      |
| AUTH_INVALID            |        —        |                 ✓                  |            ✓             |  **provider**  |
| MODEL_UNAVAILABLE       |        —        |                 ✓                  |            ✓             |     route      |
| CONTEXT_WINDOW_EXCEEDED |        —        | ✓ (larger-context candidates only) |            —             |       —        |
| CAPABILITY_UNSUPPORTED  |        —        |                 ✓                  |            —             |       —        |
| MALFORMED_RESPONSE      |        ✓        |                 ✓                  |            —             |       —        |
| CONTENT_REFUSAL         |        —        |                 ✓                  |            —             |       —        |
| INTERNAL_ERROR          |        —        |                 —                  | — (surfaces immediately) |       —        |

Exceptions: `AttemptFailed` (one attempt), `ContextWindowExceeded` (nothing fits — content is **never truncated**, R2), `AllCandidatesFailed` (chain exhausted; carries the full provenance trail).

## The routing walk

For one `LLMRequest`:

1. Resolve pool from `TASK_POOL_MAP`; acquire the pool's semaphore slot.
2. Build the candidate list from the pool's adapters (each adapter reports concrete `RouteCandidate`s; keyless adapters contribute none) and apply the ranker hook (`quota_aware_ranker` in production).
3. Skip candidates whose context window can't fit the estimated tokens; skip candidates in cooldown (`"cooling down"` appears in `routing_path`).
4. Attempt the candidate. On failure, consult the policy table: maybe retry the same route once, maybe start a cooldown, then advance.
5. First success wins. Every attempt — kind, provider, model, latency — lands in the `ProvenanceRecord`, which is delivered to the sink on success _and_ failure.

## Cooldowns

Default 60 s, monotonic-clock based with an injectable clock for tests. Cooldowns are **persisted** (`model_registry.cooldown_until` via `CooldownStore`) and restored at startup, so a restart doesn't hammer a provider that was rate-limiting us seconds ago.

**Scope (added 2026-09-06):** each cooling policy carries a `cooldown_scope`. `route` cools one `(provider, model)`; `provider` cools every model of that provider under the key `(provider, "*")`, because RATE_LIMITED / QUOTA_EXHAUSTED / AUTH_INVALID are account-level signals — sibling models share the same key and the same fate, so advancing to `provider/other-model` would only burn another attempt. SERVER_ERROR / PROVIDER_UNAVAILABLE / MODEL_UNAVAILABLE stay route-scoped (a 5xx on one model says nothing about its siblings). Provider-wide cooldowns show up in `routing_path` as `cooling down for Ns more (provider-wide)` and persist/load with model `*`.

## Attempt budgets vs. freellmpool's internal failover (added 2026-09-06)

freellmpool applies its `timeout` argument **per inner target**: when `freellmpool/auto` fails over internally across N providers, one BebshaX "attempt" could stretch to N × budget and starve the interactive path. `FreellmpoolAdapter.complete()` therefore wraps `pool.achat()` in `asyncio.wait_for(..., timeout=attempt_timeout_s(task))` so the per-task budget ([Latency budgets](#latency-budgets-llmlatencypy)) bounds the attempt as a whole; expiry maps to `TIMEOUT` (advance, no cooldown) with `"attempt budget exceeded"` in the attempt record.

## Context budgeting (`llm/estimator.py`)

`tokens ≈ chars/3.5 + 4 per message + expected output (default 1024)`. The estimate deliberately over-counts: the failure mode is steering to a roomier model, never silent truncation. If no candidate fits, `ContextWindowExceeded` is raised with `largest_window` and `estimated_tokens` — the model is never called with a shrunken prompt.

## Latency budgets (`llm/latency.py`)

Per-task attempt timeouts, applied to remote adapters only: interactive 25 s (interview, response, memory, emergency), standard 75 s, long-context 150 s (report generation), default 90 s.

## Offline behavior

Offline persona selection separately requires its compatible local ML bundle,
not Ollama. Package installation and cached demo content do not supply weights;
see [SETUP.md](SETUP.md#persona-ml-artifact). The behavior below concerns LLM
requests only.

With no network: remote attempts fail fast (CONNECTION → retry once → advance), cooldowns quiet the dead routes, and the local pool serves via Ollama (`llama3.2:3b` primary, `qwen3:4b` secondary — chosen for the 4 GB VRAM dev GPU). Without Ollama, requests fail **explicitly** with `AllCandidatesFailed`; the demo's cached content is unaffected ([DEMO.md](DEMO.md) §6).

## Acceptance coverage

Every scenario in the Phase 14 acceptance matrix maps to named tests (see the acceptance table in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)); chaos paths run against `FakeAdapter`, never real providers (R7).
