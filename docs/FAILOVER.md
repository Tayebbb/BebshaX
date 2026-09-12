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

Order is enforced between eligible tiers after privacy, capability, context,
quota and cooldown checks. A ranker cannot promote the secondary over an
eligible primary. These are the current owner-approved remote-only tables.

| Pool         | Adapter order                         | max_concurrency |
| ------------ | ------------------------------------- | --------------- |
| reasoning    | freellmpool, openrouter                | 2               |
| conversation | freellmpool, openrouter                | 5               |
| long_context | freellmpool, openrouter                | 2               |
| structured   | freellmpool, openrouter                | 3               |
| fast         | freellmpool, openrouter                | 5               |
| emergency    | freellmpool, openrouter                | 2               |

There is no active `local` pool. Local/cloud Ollama and nested OpenRouter are
excluded from primary dispatch. Historical 2026-08-26/27 local-first measurements
(one persona, five questions; local scores 9.65 / 9.05 / 9.2 versus remote
8.25 / 8.05 / 8.2) remain historical evidence, not current routing policy or a
remote availability/quality guarantee.

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

Request cancellation is not a new failure kind or evidence of degraded provider
health. The owned evaluator leaves aborted observations unknown while retaining
their consumption/provenance. Shared health aggregation still needs its owner's
matching cancellation filter; see the [current handoff](ROUTING.md#api-contract-changes-2026-09-10).

## The routing walk

For one `LLMRequest`:

1. Snapshot trusted server ownership/classification and effective processing
	policy; begin one absolute monotonic deadline before queueing or discovery.
2. Resolve `TASK_POOL_MAP` and acquire admission within that deadline. Discover
	tiers lazily, so primary success does not wait for secondary discovery.
3. Admit only explicitly approved destinations with verified context and required
	capabilities, available account allowance and expired cooldowns. A key is
	configuration, not private-data consent. Unknown context does not fit.
4. Apply the ranker within tier priority, attempt with remaining time, and consult
	the closed policy on failure. Full persona/history/evidence remains intact.
5. Nonempty stream text commits the route: failures after it never fall back.
	Terminal validation and awaited provenance persistence precede completion
	acknowledgement. A persistence error is not a provider failure to retry.

## Cooldowns

Default 60 s, monotonic-clock based with an injectable clock for tests. Cooldowns are **persisted** (`model_registry.cooldown_until` via `CooldownStore`) and restored at startup, so a restart doesn't hammer a provider that was rate-limiting us seconds ago.

Numeric/date `Retry-After` and supported reset hints extend the deadline using
the maximum; shorter or out-of-order updates never shorten it. Explicit hinted
or restored cooldowns cannot be bypassed by a half-open probe. Atomic persistence
is covered by local storage tests; live cross-worker refresh and distributed
account admission still need independent PostgreSQL verification.

**Scope (added 2026-09-06):** each cooling policy carries a `cooldown_scope`. `route` cools one `(provider, model)`; `provider` cools every model of that provider under the key `(provider, "*")`, because RATE_LIMITED / QUOTA_EXHAUSTED / AUTH_INVALID are account-level signals — sibling models share the same key and the same fate, so advancing to `provider/other-model` would only burn another attempt. SERVER_ERROR / PROVIDER_UNAVAILABLE / MODEL_UNAVAILABLE stay route-scoped (a 5xx on one model says nothing about its siblings). Provider-wide cooldowns show up in `routing_path` as `cooling down for Ns more (provider-wide)` and persist/load with model `*`.

## Attempt budgets vs. freellmpool's internal failover (added 2026-09-06)

Freellmpool's SDK timeout is per inner target. The governed adapter additionally
bounds the whole attempt by the remaining request deadline. Transport/event
hooks retain the active target on cancellation and unknown consumption without
inventing provider failure or endpoint latency. A non-cooperative task retains
admission until it really stops; owned drain is visible to shutdown and can
outlast the response deadline. No installed SDK file is patched.

## Context budgeting (`llm/estimator.py`)

The shared estimator counts ASCII at chars/3.5, non-ASCII at one token per
character, four framing tokens per message, requested output (default 1024),
and a 10% margin. It is a heuristic, not proof against every model tokenizer;
provider context rejection remains explicit. No candidate may use an invented
context window. If nothing fits, `ContextWindowExceeded` reports the largest
verified window and estimated tokens without shrinking the prompt.

## Latency budgets (`llm/latency.py`)

The task-class tables in [latency.py](../apps/backend/bebshax/llm/latency.py)
define total and per-attempt limits. One request deadline includes admission,
discovery, completion/stream reads and finalization; late success is rejected.
Native OpenRouter streaming and buffered Freellmpool delivery are labeled
separately. Page readiness, genuine first text and durable completion are
different measurements; no live latency budget is certified by fake tests.

## Offline behavior

Offline persona selection separately requires its compatible local ML bundle,
not Ollama. Package installation and cached demo content do not supply weights;
see [SETUP.md](SETUP.md#persona-ml-artifact). The behavior below concerns LLM
requests only.

With no approved, available remote route, live inference fails explicitly with
`AllCandidatesFailed` (or `ContextWindowExceeded` when verified windows cannot
fit). There is no Ollama fallback and no hidden cached-answer replacement.
Labeled demo artifacts and CPU persona selection are separate capabilities.

## Acceptance coverage

Every scenario in the Phase 14 acceptance matrix maps to named tests (see the acceptance table in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)); chaos paths run against `FakeAdapter`, never real providers (R7).

Current continuation evidence is separate from historical acceptance: **590 LLM
tests** and **37 owned API tests** passed on Python 3.12.9; the API module coverage
gate passed at **84.60%**. Exact commands, failures repaired and unresolved
RT/cross-owner gates are in [ROUTING.md](ROUTING.md#maintenance-evidence-2026-09-10).
This is not a full-backend, live-provider, proxy or PostgreSQL release verdict.
