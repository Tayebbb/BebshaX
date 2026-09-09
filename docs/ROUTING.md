# BebshaX — Routing

How an LLM request travels through BebshaX, and why the routing dependencies were chosen.

**Persona ML boundary (2026-09-09):** business, study/jobs/regeneration, workflow
role, and dataset persona generation use the shared CPU `MLPersonaAdapter`, not
this request path. No LLM call or fallback writes those profiles. Copilot context,
role suggestions, interviews, memory, and other LLM features keep the existing
router. Source/model provenance is stored with the persona; it is not a synthetic
`llm_requests` entry. See [PERSONA_ENGINE.md](PERSONA_ENGINE.md).

## Request path (current, Phase 5)

```
LLM caller (copilot, interview, research, report, compatibility code, ...)
  → PoolRouter.complete(LLMRequest{task, ...})                       [bebshax/llm/router.py]
      task → pool (config map, all 18 task types)                    [bebshax/llm/pools.py]
      per-pool asyncio.Semaphore (concurrency limits)
      candidates gathered from the pool's adapters in preference order
      pre-flight: cooldown check + capability filter + token estimate [bebshax/llm/estimator.py]
          (ineligible routes NEVER called; nothing fits → ContextWindowExceeded)
      per-failure-kind fallback (FAILURE_POLICIES) + route cooldowns  [bebshax/llm/failures.py]
      full ProvenanceRecord incl. pool, on success AND failure        [bebshax/llm/provenance.py]
  → ProviderAdapter (boundary — RULES.md R1)                          [bebshax/llm/adapters/]
      FreellmpoolAdapter → freellmpool AsyncPool.achat()
          virtual route "freellmpool/auto"; provider-level failover /
          quotas / circuit breaking happen inside freellmpool;
          the Reply's concrete provider/model lands in provenance
      OllamaAdapter → local reliability fallback (native /api/chat)
```

Wired in `create_app` lifespan: `app.state.llm_router = PoolRouter(build_default_adapters())`.
`SingleAdapterLLMService` remains for tests and smoke scripts.

## Pools and task mapping (Phase 5)

| Pool           | Adapter order                          | Concurrency | Tasks                                                                                                                             |
| -------------- | -------------------------------------- | ----------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `reasoning`    | openrouter† → freellmpool → ollama     | 2           | PERSONA_GENERATION, PERSONA_REFINEMENT, PERSONA_VALIDATION, CONTRADICTION_CHECK, CRITIC, PERSONA_NARRATIVE, BEHAVIORAL_SIMULATION |
| `conversation` | **openrouter → freellmpool → ollama**  | 5           | PERSONA_INTERVIEW, PERSONA_RESPONSE                                                                                               |
| `structured`   | openrouter† → freellmpool → ollama     | 3           | STRUCTURED_OUTPUT, EVIDENCE_EXTRACTION, EVIDENCE_CLASSIFICATION, BROWSER_AGENT, TOOL_CALLING                                      |
| `fast`         | **openrouter → freellmpool → ollama**  | 5           | MEMORY_RETRIEVAL, MEMORY_SUMMARIZATION                                                                                            |
| `long_context` | openrouter† → freellmpool → ollama     | 2           | REPORT_GENERATION                                                                                                                 |
| `local`        | ollama                                 | 2           | (reserved for explicit local-only calls)                                                                                          |
| `emergency`    | **ollama → freellmpool** (local-first) | 2           | EMERGENCY_FALLBACK                                                                                                                |

`PERSONA_GENERATION`, `PERSONA_REFINEMENT`, and `PERSONA_VALIDATION` remain in
the exhaustive task map for compatibility. Their presence does not mean the
production persona-generation routes still invoke an LLM. A missing/invalid ML
artifact yields 503; an unsupported/exhausted selection yields 422, not a router
attempt, cooldown, or LLM fallback.

† **OpenRouterAdapter is a TESTING-ONLY first preference** (owner decision 2026-08-26). Keyless → it contributes no routes and the pool behaves as before. Free-tier reality at $0: 20 req/min, 50 req/day (extra accounts do not raise limits); paid `openrouter/auto` was removed from freellmpool's override list — do not fund the key. Its pool position contradicts D1/the capacity plan and must be revisited before production (`docs/AI_IMPLEMENTATION_PLAN.md` §10).

**OpenRouter free catalogue is discovered, not hard-coded (2026-09-08).** The previous three `:free` seeds had all been delisted (404 → `MODEL_UNAVAILABLE` → three dead attempts and three 60 s cooldowns per request). With a key present the production adapter (`OpenRouterAdapter(discover_catalogue=True)`, wired only in `adapters/factory.py`) fetches the public `/api/v1/models` catalogue (no key needed), keeps the `:free` chat models (safety/code/reasoning families excluded), prefers routes that accept `response_format`, then larger context windows, and offers the top 4 with their real context windows and capability flags. Cached 30 min; a failed refresh keeps the last good list and records the error. Precedence: `BEBSHAX_OPENROUTER_MODELS` pin → discovered catalogue → `DEFAULT_MODELS` seed (offline only). `GET /api/health/openrouter` reports `catalogue` (pinned / discovered / error). Unit tests never discover (default off).

**Interactive pools now prefer OpenRouter (owner decision 2026-09-09).** `conversation`/`fast` were previously local-first, locked by the 2026-08-26/27 judged gate below. In practice local `ollama/llama3.2:3b` measured **14-24 s/turn** on the dev machine under real load (VRAM/RAM pressure), so interactive replies now put OpenRouter's fast free models first; Ollama stays **last** as the on-machine fallback so cross-adapter failover still terminates locally. The gate data is kept for the record — it does not describe the current order:

**Latency stack (2026-08-26/27, judged gate — all three runs, HISTORICAL):** `ollama/llama3.2:3b` (arm A) vs the `freellmpool/fast` cloud route (arm B), blind LLM judge, 8/10 production bar, **n = 1 persona × 5 questions per run** (`scripts/judge_local_interview.py`; artifacts `data/metadata/local_3b_gate_*.json`):

| Run              | A weighted / avg s/turn | B weighted / avg s/turn | B served by                                   | Judge route           | Caveat                                                                              |
| ---------------- | ----------------------- | ----------------------- | --------------------------------------------- | --------------------- | ----------------------------------------------------------------------------------- |
| 2026-08-26 23:56 | **9.65** / 6.1 s        | 8.25 / 53.0 s           | kilo/stepfun step-3.7-flash, llm7/codestral   | llm7/codestral-latest | judge model also served part of arm B (self-preference risk, unflagged at the time) |
| 2026-08-27 10:19 | **9.05** / 6.8 s        | 8.05 / 2.5 s            | llm7/codestral-latest                         | llm7/codestral-latest | judge == arm B model for every turn; B was _faster_ than local in this run          |
| 2026-08-27 11:45 | **9.2** / 4.8 s         | 8.2 / 56.3 s            | kilo/stepfun step-3.7-flash, ovh/Mistral-Nemo | llm7/codestral-latest | `self_preference_risk: false` — the only run with no judge/arm overlap              |

Reading: local clears the 8/10 bar in all three runs and beats cloud-fast on quality by ~1 point each time, but this is a small-n gate (one persona, five questions, one judge family), not a benchmark; the latency advantage is real in 2 of 3 runs and reversed in run 2. Earlier docs quoted only run 1 ("9.65 vs 53 s"). `FreellmpoolAdapter(routing="fast")` enables freellmpool's smoothed-latency-first ranking; per-task attempt budgets live in `bebshax/llm/latency.py` (interactive 25 s / standard 75 s / long-context 150 s → TIMEOUT advances the candidate chain). The repo's `providers.toml` is now actually loaded (`FREELLMPOOL_CONFIG` set by `bebshax.main`); it removes Kilo's double-proxy routes (`openrouter/free`, `kilo-auto/free`) and the 185 s nemotron-120b, and keeps only measured-fast OpenRouter models.

- Every pool includes the local adapter. Emergency is local-first; conversation/fast/reasoning/structured/long-context put Ollama last, as shown in the source-backed table above.
- **Ranking:** pool/adapter order today; `PoolRouter(ranker=...)` is the hook where Phase-6 registry scores (quality/latency/health) and Phase-11 strategy experiments plug in.
- **Cooldowns:** failure kinds with `cooldown_route=True` (429, quota, 5xx, auth, provider/model unavailable) cool the route for 60 s (TIMEOUT: 30 s, `FailurePolicy.cooldown_seconds`); RATE_LIMITED / QUOTA_EXHAUSTED / AUTH_INVALID are **provider-scoped** (key `(provider, "*")`, added 2026-09-06) because they are account-level signals, the rest are route-scoped `(provider, model)`. Cooling routes are skipped with a routing-path note (`(provider-wide)` suffix for provider scope) and return automatically; state persists in `model_registry.cooldown_until` via `CooldownStore` and is restored at startup ([FAILOVER.md](FAILOVER.md) § Cooldowns).
- **Cooldown probe (half-open breaker, 2026-09-08):** when cooldowns alone leave a pool with nothing eligible, the router does **not** fail in 0 ms. The routes that are capable, fit the context and are not already being probed are admitted in order of soonest recovery (`[cooldown probe: …]` in the routing path), one in-flight probe per route; a probe that fails re-arms its cooldown normally. Observed live before the fix: a single 75 s freellmpool timeout benched the only keyless route and every feature returned `all_candidates_failed` instantly for 30 s. Capability and context exclusions are never overridden.
- **Token estimator:** deterministic chars/3.5 + 4 tokens/message overhead + expected output — deliberately over-estimates so mis-sizing can only pick a roomier model, never truncate.
- Tool-requiring tasks map to `structured` but no adapter advertises tool support yet → they fail explicitly (`AllCandidatesFailed`) until tool plumbing lands (honest by design).

## Failure classification

| freellmpool / transport outcome                    | BebshaX `FailureKind`     | Policy                                              |
| -------------------------------------------------- | ------------------------- | --------------------------------------------------- |
| `ContextWindowExceeded` (caught before its parent) | `CONTEXT_WINDOW_EXCEEDED` | advance to larger-context candidate; never truncate |
| `AllProvidersExhausted` (client_status=429)        | `RATE_LIMITED`            | advance + cooldown                                  |
| `AllProvidersExhausted` (other)                    | `PROVIDER_UNAVAILABLE`    | advance + cooldown                                  |
| `NoProvidersConfigured`                            | `PROVIDER_UNAVAILABLE`    | advance + cooldown                                  |
| `ProviderHTTPError` 401/403                        | `AUTH_INVALID`            | advance + cooldown                                  |
| `ProviderHTTPError` 404                            | `MODEL_UNAVAILABLE`       | advance + cooldown                                  |
| `ProviderHTTPError` 5xx                            | `SERVER_ERROR`            | advance + cooldown                                  |
| `httpx.TimeoutException`                           | `TIMEOUT`                 | advance                                             |
| `httpx.TransportError`                             | `CONNECTION`              | retry same once, then advance                       |
| empty/whitespace reply                             | `MALFORMED_RESPONSE`      | retry same once, then advance                       |

OpenRouter-specific (2026-09-08, `openrouter_adapter._map_http_status`): a 429 whose body names one model's **upstream shared pool** (`limit_source=upstream_provider_shared_pool`, "…is temporarily rate-limited upstream") is `MODEL_UNAVAILABLE` (route-scoped cooldown) — only an account-level 429 is `RATE_LIMITED` (provider-wide). Routes whose catalogue entry exposes the `reasoning` toggle are called with `reasoning: {enabled: false}`; a reply with no content after N reasoning tokens is still `MALFORMED_RESPONSE`, with the token count and `finish_reason` in the attempt detail.

Low answer quality is deliberately absent — it is handled by the evaluation layer (Phase 11), never by infrastructure fallback (RULES.md R2).

## Dependency review (RULES.md R8)

### freellmpool 0.11.4 — ADOPTED (Phase 3)

- **Why needed:** aggregates legitimate free LLM providers (18 in the catalog bundled with the pinned 0.11.4 — verified 2026-08-28, re-verified 2026-09-06; the "~24 providers / 222 routes" in earlier docs came from the 2026-08-22 audit of the upstream project and does not describe what is installed; the repo's own `providers.toml` only overrides `kilo` and `openrouter`) behind one API with failover, per-key quota tracking, Retry-After-aware cooldowns, per-route circuit breakers, context-limit learning, and keyless start. This _is_ the "aggregate free capacity" requirement.
- **What it replaces:** building our own multi-provider router/gateway (explicitly forbidden by the brief §42 / owner rule #12).
- **License:** MIT. **Activity:** v0.11.4 on PyPI, commits within 3 weeks of adoption, CI, security policy. **Risk:** small project (single-maintainer) → mitigated by the adapter boundary; it is swappable without touching application code, and MIT allows vendoring.
- **Runtime deps:** `httpx` only.
- **Necessity check:** compared against freelm, free-model-router, freerouter, NadirClaw, APIKeyRotator — all strict subsets or wrong-focus (see audit §6.1). Verified live 2026-08-22: keyless completion served by `llm7/codestral-latest` with 3 internal failover attempts, zero keys configured.

### Gate B — LiteLLM: **SKIPPED** (decision recorded 2026-08-22)

- The needed provider surface (Groq, Gemini, NVIDIA NIM, Mistral, Cerebras, OpenRouter, Cohere, GitHub Models, Cloudflare, HF router + keyless tiers + Ollama) is fully covered by freellmpool + a native Ollama adapter.
- LiteLLM's proxy/gateway would add Postgres/Prisma/Redis-scale infrastructure for capabilities we already have; the SDK alone would duplicate freellmpool's dispatch.
- **Revisit trigger:** a concretely required provider/endpoint that freellmpool cannot reach. The adapter boundary makes a later `LiteLLMAdapter` a drop-in.

## Provider configuration

- Keys are environment variables only (see [.env.example](../.env.example)); freellmpool reads standard names (`GROQ_API_KEY`, `GEMINI_API_KEY`, `NVIDIA_API_KEY`, ...). Multiple keys per provider: comma-separated. Zero keys is a supported configuration (keyless providers).
- The BebshaX app never hard-codes a provider list (owner decision #10); enabling/disabling providers is freellmpool configuration (`providers.toml` / env), surfaced later via the model registry (Phase 5/6).
- Routing mode: `FreellmpoolAdapter(routing=...)` accepts freellmpool modes (`quality`, `fast`, `fair`, ...); the existing `TASK_POOL_MAP` chooses BebshaX pools, separately from freellmpool's internal ranking mode.

## Local fallback (Ollama) — Phase 4

- **Adapter:** `bebshax/llm/adapters/ollama_adapter.py` — plain `httpx` against Ollama's **native `/api/chat`** (no SDK dependency). _Deliberate spec deviation:_ the OpenAI-compat endpoint cannot set `options.num_ctx`, and Ollama silently truncates prompts beyond the runtime context — so the adapter pins `num_ctx` to a generous per-request estimate (chars/3 + output + headroom) and **refuses** (`CONTEXT_WINDOW_EXCEEDED`) instead of ever truncating (R2).
- **Candidates:** discovered live from `/api/tags` with honest per-model windows from `/api/show`, capped at 16k for the 4 GB card, **sorted smallest-first** — under RAM pressure the small model is the one most likely to load, and resilience is this tier's job.
- **Measured on the dev machine (2026-08-22, 3-run medians, `data/metadata/ollama_benchmark.json`):**

| Model            | Size   | Status                                                                             | tok/s            | TTFT        |
| ---------------- | ------ | ---------------------------------------------------------------------------------- | ---------------- | ----------- |
| `llama3.2:3b`    | 2.0 GB | ✅ primary local fallback                                                          | 25.2 (59.8 warm) | ~2.8 s cold |
| `qwen3:4b`       | 2.5 GB | ✅ secondary (better quality, needs more staging RAM)                              | 22.4             | 217 ms warm |
| `qwen3.5:latest` | 6.6 GB | ❌ **unusable under real load** — HTTP 500 / runner OOM with <2 GB free system RAM | —                | —           |

- **Finding:** with VS Code + browser + Docker running, free RAM sits near 1–2 GB, so the 6.6 GB model cannot load (`"model requires more system memory (1.8 GiB) than is available"` was observed even for the 2.5 GB model until WSL was shut down). The fully-GPU-resident small models are therefore the _only_ dependable local tier; `qwen3.5` remains installed but the router's TIMEOUT/SERVER_ERROR policies simply advance past it when it fails.
- Ops note: `wsl --shutdown` frees the Docker VM's RAM when the local tier is needed and Docker isn't (Docker restarts on demand for Phase 6 work).
- Ops note (H2, 2026-08-26): the Ollama daemon has **no autostart** on the dev machine — after a reboot run `ollama serve` (or launch the desktop app). The backend logs a startup WARNING and sets `app.state.local_tier_up=False` when the local tier contributes no routes.

## Verification

The 2026-09-09 ML continuation recorded seven successful Freellmpool responses
served by `llm7/codestral-latest` through `freellmpool/auto`, for copilot context,
role suggestions, and two interview turns. Existing OpenRouter quota cooldown
was observed. Seven successes in this smoke sample are not a measured provider
success rate or a cross-route benchmark. Persona selection made zero LLM calls.
Historical local-model latency/quality tables above retain their original dates
and small-sample limits; ML warm-selection latency is not LLM/API latency.

- Unit (no network): `apps/backend/tests/llm/test_freellmpool_adapter.py` (error mapping, parameter passthrough, concrete-route provenance), `test_ollama_adapter.py` (mock-transport error mapping, candidate discovery/caps, `num_ctx` passthrough, oversize refusal), `test_boundary.py` (R1 enforcement).
- Live keyless smoke: `python scripts/smoke_freellmpool.py`.
- Live local smoke: `python scripts/smoke_ollama.py`; benchmarks: `python scripts/benchmark_ollama.py`.
