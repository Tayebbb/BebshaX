# Failover & Routing

The complete failure-handling contract: pools, the task map, the closed failure taxonomy, cooldowns, and context budgeting. Strategy background lives in [ROUTING.md](ROUTING.md); architecture context in [ARCHITECTURE.md](ARCHITECTURE.md).

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

`conversation` is local-first by measurement, not ideology: the 2026-08-26 gate scored `llama3.2:3b` 9.65/10 on interview quality at ~6 s/turn versus ~53 s on free cloud tiers.

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

## Failure taxonomy (closed set, `llm/failures.py`)

13 kinds. **Low answer quality is deliberately not a failure kind** — it belongs to the quality/eval layer, never to routing (owner rule, 2026-08-22). New kinds require enum + policy + tests in one commit (R6).

| FailureKind             | retry same once |              try next              |         cooldown         |
| ----------------------- | :-------------: | :--------------------------------: | :----------------------: |
| TIMEOUT                 |        —        |                 ✓                  |            —             |
| CONNECTION              |        ✓        |                 ✓                  |            —             |
| RATE_LIMITED            |        —        |                 ✓                  |            ✓             |
| QUOTA_EXHAUSTED         |        —        |                 ✓                  |            ✓             |
| SERVER_ERROR            |        —        |                 ✓                  |            ✓             |
| PROVIDER_UNAVAILABLE    |        —        |                 ✓                  |            ✓             |
| AUTH_INVALID            |        —        |                 ✓                  |            ✓             |
| MODEL_UNAVAILABLE       |        —        |                 ✓                  |            ✓             |
| CONTEXT_WINDOW_EXCEEDED |        —        | ✓ (larger-context candidates only) |            —             |
| CAPABILITY_UNSUPPORTED  |        —        |                 ✓                  |            —             |
| MALFORMED_RESPONSE      |        ✓        |                 ✓                  |            —             |
| CONTENT_REFUSAL         |        —        |                 ✓                  |            —             |
| INTERNAL_ERROR          |        —        |                 —                  | — (surfaces immediately) |

Exceptions: `AttemptFailed` (one attempt), `ContextWindowExceeded` (nothing fits — content is **never truncated**, R2), `AllCandidatesFailed` (chain exhausted; carries the full provenance trail).

## The routing walk

For one `LLMRequest`:

1. Resolve pool from `TASK_POOL_MAP`; acquire the pool's semaphore slot.
2. Build the candidate list from the pool's adapters (each adapter reports concrete `RouteCandidate`s; keyless adapters contribute none) and apply the ranker hook (`quota_aware_ranker` in production).
3. Skip candidates whose context window can't fit the estimated tokens; skip candidates in cooldown (`"cooling down"` appears in `routing_path`).
4. Attempt the candidate. On failure, consult the policy table: maybe retry the same route once, maybe start a cooldown, then advance.
5. First success wins. Every attempt — kind, provider, model, latency — lands in the `ProvenanceRecord`, which is delivered to the sink on success _and_ failure.

## Cooldowns

Default 60 s per `(provider, model)`, monotonic-clock based with an injectable clock for tests. Cooldowns are **persisted** (`model_registry.cooldown_until` via `CooldownStore`) and restored at startup, so a restart doesn't hammer a provider that was rate-limiting us seconds ago.

## Context budgeting (`llm/estimator.py`)

`tokens ≈ chars/3.5 + 4 per message + expected output (default 1024)`. The estimate deliberately over-counts: the failure mode is steering to a roomier model, never silent truncation. If no candidate fits, `ContextWindowExceeded` is raised with `largest_window` and `estimated_tokens` — the model is never called with a shrunken prompt.

## Latency budgets (`llm/latency.py`)

Per-task attempt timeouts, applied to remote adapters only: interactive 25 s (interview, response, memory, emergency), standard 75 s, long-context 150 s (report generation), default 90 s.

## Offline behavior

With no network: remote attempts fail fast (CONNECTION → retry once → advance), cooldowns quiet the dead routes, and the local pool serves via Ollama (`llama3.2:3b` primary, `qwen3:4b` secondary — chosen for the 4 GB VRAM dev GPU). Without Ollama, requests fail **explicitly** with `AllCandidatesFailed`; the demo's cached content is unaffected ([DEMO.md](DEMO.md) §6).

## Acceptance coverage

Every scenario in the Phase 14 acceptance matrix maps to named tests (see the acceptance table in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)); chaos paths run against `FakeAdapter`, never real providers (R7).
